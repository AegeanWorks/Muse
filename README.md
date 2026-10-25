# muse

[![Built with AIKit](https://img.shields.io/badge/built%20with-AIKit-6f42c1)](https://github.com/AegeanWorks/AIKit)

Prompt-driven AI music creation with an automated listener that scores how well each track fits the theme, exposed as a CLI and Python library.

## ⚡ 30-Second Cold-Start Quick Reference

- **Runtime Prerequisites**: <FILL: each runtime this project needs and its minimum version>
- **Canonical Regression Shield Gate**:
  ```bash
  python -m unittest discover -s tests -t .
  ```

### 🛠️ AIKit Commands (run from the AIKit folder)
| Role | Command |
|---|---|
| Status, task and gates | `python aikit.py status muse` |
| Phase 4: every gate | `python aikit.py check muse` |
| Repair memory and map, then check | `python aikit.py fix muse` |
| Resume an interrupted task | `python aikit.py resume muse` |

## 📦 What's Inside

```text
muse/
├── .gitignore                <- transient AIKit state excluded
├── LICENSE                   <- Aegean License 1.0 (AL-1.0): free personal use
├── COMMERCIAL.md             <- Commercial licensing terms
├── README.md
└── .aikit/                   <- this project's memory: record, ledger, decisions
```

## 📜 License

Free for personal use under the Aegean License 1.0 (AL-1.0); see [LICENSE](LICENSE). Any commercial use needs the Aegean Commercial License 1.0 (ACL-1.0); see [COMMERCIAL.md](COMMERCIAL.md).
