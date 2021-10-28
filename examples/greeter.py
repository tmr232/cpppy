from cpp import magic


class Greeter:
    # First, a private member variable
    name: str

    public()

    # Then some public methods

    def Greeter(name):
        # Good Python is selfless Python
        this.name = name
        print(f"Hello, {this.name}!")

    def _Greeter():
        # Yes, this is a destructor
        # Pretend the _ is a ~
        print(f"Goodbye, {this.name}.")


# This is the main function. It just runs.
# Calling it explicitly would be silly.
def main():
    greeter1 = Greeter(1)
    greetee2 = Greeter(2)
