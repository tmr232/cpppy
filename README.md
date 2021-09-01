# cpp.py

Implementing C++ Semantics in Python

## Disclaimer

This project is an experiment.

Please don't use it in any sensitive context.

## Installation

### From PyPI

```shell
pip install cpppy
```

### From Source (Dev)

```shell
git clone https://github.com/tmr232/cpppy.git
cd cpppy
poetry install
poetry shell
```

## Usage & Examples

Import `magic` inside a module and watch the magic happen.

Note that it only works inside modules.
Importing it in an interactive shell or a Jupyter Notebook won't work.

That said, functions from said modules can be imported and used
in regular Python code. 

```python
# examples/greeter.py

from cpp import magic


class Greeter:
    name: str

    public()

    def Greeter(name):
        this.name = name
        print(f"Hello, {this.name}!")

    def _Greeter():
        print(f"Goodbye, {this.name}.")


def main():
    greeter1 = Greeter(1)
    greetee2 = Greeter(2)

```

```shell
>>> python examples/greeter.py
Hello, 1!
Hello, 2!
Goodbye, 2.
Goodbye, 1.
```

## Presentations

* [Implementing C++ Semantics in Python](https://github.com/tmr232/talks/tree/main/CoreCpp2021) (Core C++ 2021)