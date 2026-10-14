"""A two-layer neural network with hand-written backpropagation."""

import math
import random


def sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


class TinyNet:
    def __init__(self, n_in, n_hidden, seed=0):
        rng = random.Random(seed)
        self.w1 = [[rng.uniform(-1, 1) for _ in range(n_in)] for _ in range(n_hidden)]
        self.w2 = [rng.uniform(-1, 1) for _ in range(n_hidden)]

    def forward(self, x):
        self.x = x
        self.h = [sigmoid(sum(w * xi for w, xi in zip(row, x))) for row in self.w1]
        self.y = sigmoid(sum(w * hi for w, hi in zip(self.w2, self.h)))
        return self.y

    def backward(self, target, lr=0.5):
        # dL/dy for squared error, times sigmoid'(z) = y(1-y)
        delta_out = (self.y - target) * self.y * (1 - self.y)
        grad_w2 = [delta_out * hi for hi in self.h]
        delta_hidden = [delta_out * w * hi * (1 - hi) for w, hi in zip(self.w2, self.h)]
        for j, row in enumerate(self.w1):
            for i in range(len(row)):
                row[i] -= lr * delta_hidden[j] * self.x[i]
        self.w2 = [w - lr * g for w, g in zip(self.w2, grad_w2)]
