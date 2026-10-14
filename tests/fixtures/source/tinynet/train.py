"""Train TinyNet on XOR."""

from tinynet.model import TinyNet

DATA = [([0, 0], 0), ([0, 1], 1), ([1, 0], 1), ([1, 1], 0)]


def train(epochs=5000):
    net = TinyNet(n_in=2, n_hidden=4)
    for _ in range(epochs):
        for x, y in DATA:
            net.forward(x)
            net.backward(y)
    return net


if __name__ == "__main__":
    net = train()
    for x, y in DATA:
        print(x, y, round(net.forward(x), 3))
