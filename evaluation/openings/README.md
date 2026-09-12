# Evaluation opening suite

SixtyFour's default strength evaluation uses
`4mvs_+90_+99.epd` from the official Stockfish books repository. The upstream
metadata identifies 635 standard-chess positions, each reached after eight
plies. That is enough for the 200-paired-opening release study while keeping the
starting positions shallow enough to test most of each game.

Every selected position is played twice with colors reversed. The suite is
match input only: Arasan's own opening book remains disabled.

## Provenance

- repository: <https://github.com/official-stockfish/books>
- pinned revision: `65815ccdbc7727cd4f6aee252ba8f67fb740e92f`
- upstream archive:
  <https://raw.githubusercontent.com/official-stockfish/books/65815ccdbc7727cd4f6aee252ba8f67fb740e92f/4mvs_%2B90_%2B99.epd.zip>
- upstream archive SHA-256:
  `733be6809d849e75d590e1fce7dea1540aecac5b2d89b15cda50969e269c1989`
- extracted upstream EPD SHA-256 before line-ending normalization:
  `9b4d9fb7eda778377a36f67c93b6913b67c6b4db9a51e1b7d9bf6bff5cdf8e8e`
- vendored EPD SHA-256 after Git's LF normalization:
  `13f1637882d3631fc6919c2c8ab95989d1e6d620a335feccc727ea1d3d63e317`
- license: CC0 1.0 Universal; see `LICENSE-CC0-1.0.txt`

The file is intentionally vendored because it is small, removes a network
dependency from local and CI evaluation, and makes historical runs reproducible.
Do not replace it in place. A corpus change is an evaluation-method change: add
or update the provenance, pin the new hash, and establish a new baseline.
