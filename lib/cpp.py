import enum
import inspect
import importlib.util
import itertools
import sys
import dataclasses
from typing import Dict

KEYWORDS = ["this", "public", "private", "protected"]
__all__ = ["magic"] + KEYWORDS

IMPORT_FLAG = "__magically_imported__"


class Access(enum.Enum):
    PRIVATE = 1
    PUBLIC = 2
    PROTECTED = 3

DEFAULT_ACCESS = Access.PRIVATE

_dtor_stack = []
_this_stack = []
_caller_stack = []

_access = {}


@dataclasses.dataclass
class ClassAccess:
    current: Access = DEFAULT_ACCESS
    members: Dict[str, Access] = dataclasses.field(default_factory=dict)


class ThisProxy:
    def __getattr__(self, name):
        return getattr(_this_stack[-1], name)

    def __setattr__(self, name, value):
        setattr(_this_stack[-1], name, value)


class ThisScope:
    def __init__(self, instance):
        _this_stack.append(instance)

    def __enter__(self):
        return

    def __exit__(self, exc_type, exc_val, exc_tb):
        _this_stack.pop()


this = ThisProxy()


def reset_access(cls):
    class_name = cls.__name__

    if class_name in _access:
        _access.pop(class_name)


def set_access(access: Access):
    locals = inspect.stack()[2].frame.f_locals
    annotations = locals.get("__annotations__", {})
    class_name = locals["__qualname__"]

    class_access = _access.setdefault(class_name, ClassAccess())

    for name in itertools.chain(locals, annotations):
        if name.startswith("__"):
            continue

        if name not in class_access.members:
            class_access.members[name] = class_access.current

    class_access.current = access


def get_member_access(cls, member_name):
    class_name = cls.__name__

    class_access = _access.get(class_name, ClassAccess())

    return class_access.members.get(member_name, class_access.current)


def public():
    set_access(Access.PUBLIC)


def private():
    set_access(Access.PRIVATE)


def protected():
    set_access(Access.PROTECTED)


def may_access(caller, target, required_access):
    if caller is None:
        # We're calling from pure-Python, so we allow all :P
        return True

    if required_access == Access.PUBLIC:
        return True

    if required_access == Access.PROTECTED:
        return isinstance(caller.instance, target.__class__)

    if required_access == Access.PRIVATE:
        return type(caller) == type(target)

    return False


class IdentityComparator:
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        return self.obj is other


def get_dtor_stack():
    return _dtor_stack


class DtorScope:
    def __init__(self):
        self.stack = []
        get_dtor_stack().append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        get_dtor_stack().pop()

        while self.stack:
            self.stack.pop().__exit__(exc_type, exc_val, exc_tb)

    def push(self, cm):
        self.stack.append(cm)

    def remove(self, cm):
        self.stack.remove(IdentityComparator(cm))


def push_dtor(cm):
    return get_dtor_stack()[-1].push(cm)


def remove_dtor(cm):
    get_dtor_stack()[-1].remove(cm)


def rebind_to_parent_dtor(cm):
    if is_cpp_class(cm):
        get_dtor_stack()[-1].remove(cm)
        get_dtor_stack()[-2].push(cm)


class CallerScope:
    def __init__(self, caller):
        _caller_stack.append(caller)

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        _caller_stack.pop()


def get_caller():
    return _caller_stack[-1]


def cpp_function(f):
    def _wrapper(*args, **kwargs):
        with CallerScope(f):
            with DtorScope():
                retval = f(*args, **kwargs)
                rebind_to_parent_dtor(retval)
                return retval

    return _wrapper


def cpp_method(f, access):
    def _wrapper(self, *args, **kwargs):
        check_access(self, access)
        with CallerScope(self):
            with ThisScope(self):
                with DtorScope():
                    retval = f(*args, **kwargs)
                    rebind_to_parent_dtor(retval)
                    return retval

    return _wrapper


class AccessError(Exception):
    pass


def check_access(target, access):
    caller = get_caller()
    if not may_access(caller, target, access):
        raise AccessError()


class CppMember:
    def __init__(self, access):
        self.access = access

    def __set_name__(self, owner, name):
        self.private_name = "_" + name

    def __get__(self, instance, owner=None):
        check_access(instance, self.access)
        return getattr(instance, self.private_name)

    def __set__(self, instance, value):
        check_access(instance, self.access)
        old = getattr(instance, self.private_name, None)

        if is_cpp_class(old):
            old.__exit__(None, None, None)

        if is_cpp_class(value):
            remove_dtor(value)

        setattr(instance, self.private_name, value)


def create_class_members(cls):
    member_names = list(getattr(cls, "__annotations__", {}))

    for name in member_names:
        member = CppMember(get_member_access(cls, name))
        member.__set_name__(cls, name)
        setattr(cls, name, member)

    setattr(cls, "__member_names__", member_names)


def decorate_class_methods(cls):
    for name, value in inspect.getmembers(cls):
        if name.startswith("__"):
            continue

        if not inspect.isroutine(value):
            continue

        setattr(cls, name, cpp_method(value, get_member_access(cls, name)))


def is_cpp_class(obj):
    return hasattr(obj, "__cpp_class__")


def cpp_class(cls):
    decorate_class_methods(cls)

    create_class_members(cls)

    def __init__(self, *args, **kwargs):
        push_dtor(self)
        ctor = getattr(self, self.__class__.__name__, None)
        if ctor:
            ctor(*args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        dtor = getattr(self, "_" + self.__class__.__name__, None)
        if dtor:
            dtor()

        with CallerScope(self):
            for name in reversed(self.__member_names__):
                value = getattr(self, name, None)
                if not is_cpp_class(value):
                    continue
                value.__exit__(None, None, None)

    cls.__init__ = __init__
    cls.__enter__ = __enter__
    cls.__exit__ = __exit__

    cls.__cpp_class__ = True

    reset_access(cls)

    return cls


def get_calling_module():
    for frameinfo in inspect.stack():
        if frameinfo.filename == __file__:
            continue

        module = inspect.getmodule(frameinfo.frame)
        if module:
            return module


def import_by_path(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    setattr(module, IMPORT_FLAG, True)
    spec.loader.exec_module(module)
    return module


def decorate_module_functions(module):
    for name, value in inspect.getmembers(module):
        if not inspect.isroutine(value):
            continue

        # Only convert functions that were defined in the importing file.
        # We don't want to convert library imports and the likes of those.
        if inspect.getmodule(value) != module:
            continue

        setattr(module, name, cpp_function(value))


def decorate_module_classes(module):
    for name, value in inspect.getmembers(module):
        if not inspect.isclass(value):
            continue

        # Only convert functions that were defined in the importing file.
        # We don't want to convert library imports and the likes of those.
        if inspect.getmodule(value) != module:
            continue

        setattr(module, name, cpp_class(value))


def inject_keywords(module):
    for name in KEYWORDS:
        setattr(module, name, globals()[name])


def _magic():
    calling_module = get_calling_module()

    inject_keywords(calling_module)

    name = calling_module.__name__
    path = calling_module.__file__
    if hasattr(calling_module, IMPORT_FLAG):
        return

    imported_module = import_by_path(name, path)

    decorate_module_functions(imported_module)
    decorate_module_classes(imported_module)

    if imported_module.__name__ == "__main__":
        sys.exit(imported_module.main())


def __getattr__(name):
    if name != "magic":
        raise AttributeError()

    _magic()
