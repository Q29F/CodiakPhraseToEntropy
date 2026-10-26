# Mathematical contract

The application connects a defined text statistic to the original phase-controlled
Codiak equation. The text adapter and the field have different meanings and are
reported separately.

## Phrase statistics and phase

Normalize the supplied string to Unicode NFC, preserving case and whitespace.
Count Unicode codepoints, including spaces and line breaks. This does not count
grapheme clusters: a displayed character can contain several codepoints.
Canonical equivalents normalize consistently under
[Python's Unicode normalization rules](https://docs.python.org/3.12/library/unicodedata.html).

For normalized length `n` and each distinct codepoint's count `count[a]`:

```text
p[a] = count[a] / n
H = -sum(p[a] * log2(p[a]))
normalizedEntropy = H / log2(n)
phase = pi * normalizedEntropy
```

`H` is the empirical character-frequency Shannon entropy in bits, using the
definition in C. E. Shannon, [A Mathematical Theory of Communication](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)
(1948). The normalization and phase mapping are choices of this adapter.
`n` means total normalized text length, not the number of distinct symbols.

Empty and single-codepoint strings return zero entropy, normalized entropy, and
phase by convention. Entropy terms use `math.fsum`. The normalized value is
clamped into `[0, 1]` to contain floating-point roundoff before phase conversion.

| Input | Length | Distinct codepoints | H, bits | Normalized H | Phase |
| --- | ---: | ---: | ---: | ---: | ---: |
| empty string | 0 | 0 | 0 | 0 | 0 |
| `aaaa` | 4 | 1 | 0 | 0 | 0 |
| `ab` | 2 | 2 | 1 | 1 | pi |
| `abab` | 4 | 2 | 1 | 0.5 | pi/2 |
| `abcd` | 4 | 4 | 2 | 1 | pi |

After NFC normalization, strings with identical codepoint counts have identical
results regardless of order. Repetition changes the length denominator even when
relative frequencies stay the same. The statistic is not semantic entropy, an
encoding of phrase meaning, or an estimate of cryptographic unpredictability.

The API accepts at most 2,048 codepoints both before and after normalization and
rejects unpaired surrogate codepoints. It does not return the raw phrase.

## Original field and numerical plot

The original symbolic model is retained:

```text
field(x,y,t) = sqrt(u(x,y,t)^2 + v(x,y,t)^2) * sin(x*y + t + phase)
```

`u` and `v` are undefined real-valued symbolic functions. The browser plot declares
the additional numerical assumption `u(x,y,t) = u0`, `v(x,y,t) = v0`, using the
user-supplied constants:

```text
field(x) = hypot(u0, v0) * sin(x*y0 + t0 + phase)
```

The plot uses 129 equally spaced samples including both endpoints of `[-pi, pi]`.
It is a sampled signed field, not the measured phrase entropy. The sample count
is fixed; the browser cannot request arbitrary expressions or unbounded work.

## Numerical input limits

- Phase is a finite real number in `[0, pi]`.
- `u0` and `v0` are finite numbers in `[-100, 100]`.
- `y0` is finite in `[-10, 10]`; `t0` is finite in `[-100, 100]`.
- Booleans, numeric strings, non-finite numbers, and unknown fields are rejected.
- A zero amplitude produces the valid all-zero field.

The phase validator and symbolic constructor are shared by the browser,
command-line examples, and notebook. Tests compare the numerical samples with
the symbolic expression after explicitly substituting the constant inputs.
