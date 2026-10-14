# The Big Picture

**Learning objectives.** After this chapter you will be able to describe what `tinynet` does, name its two modules, and trace one prediction through the code.

## What tinynet is

`tinynet` is a teaching repository: a two-layer neural network, written in plain Python, that learns the XOR function ([[README.md:1-3]]). It has no dependencies beyond the standard library, which makes every computation visible.

## The two modules

| Module | Responsibility |
|---|---|
| [[tinynet/model.py]] | The network: weights, forward pass, backward pass |
| [[tinynet/train.py]] | The data set and the training loop |

## The forward pass

A prediction is two weighted sums, each squashed by a <dfn>sigmoid</dfn>:

```python tinynet/model.py:17-21
    def forward(self, x):
        self.x = x
        self.h = [sigmoid(sum(w * xi for w, xi in zip(row, x))) for row in self.w1]
        self.y = sigmoid(sum(w * hi for w, hi in zip(self.w2, self.h)))
        return self.y
```

Note that `forward` *stores* `x`, `h` and `y` on the object. Chapter 2 shows why: the backward pass reuses them.

> [!NOTE]
> The weights are initialised from a seeded random generator ([[tinynet/model.py:13]]), so every run is reproducible.

## Exercises

> [!EXERCISE]
> How many weights does `TinyNet(n_in=2, n_hidden=4)` have?

<details>
<summary>Solution</summary>

`w1` is 4 × 2 = 8 weights and `w2` has 4, so 12 in total. There are no bias terms.

</details>
