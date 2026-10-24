# Vendored: alexforencich/verilog-uart

- Source: https://github.com/alexforencich/verilog-uart
- Commit: 1b867e53af738e4a8bc7c839ca2f1c07f40382dc (2025-02-27)
- License: MIT (see LICENSE)
- Files: rtl/uart.v, rtl/uart_rx.v, rtl/uart_tx.v, README.md copied unmodified;
  LICENSE is upstream COPYING.
- Note: upstream is deprecated in favour of https://github.com/fpganinja/taxi.

SHA-256 (verify with `shasum -a 256 -c` from this directory):

```
4f91abcd67ff180afadbad06c3b44d33c9f1d69bfaeae3b5696be112efae35c9  rtl/uart.v
e686104e5ff2d25fa1504e8d08259cef508f2ec9c9e8cfa63364f3fcb39b9f5c  rtl/uart_rx.v
e9559ddebf124f8fbface06bf7091296baa78c7acab95a36b40a919663349d34  rtl/uart_tx.v
ba534ddccb8b414208200922c54128e6db21d0923aa027dd10bb0db351ebffd0  README.md
e976f1560229f2e4259c993745637435e2d8f969c91bf73651443aea4438d142  LICENSE
```

The grader compiles these exact files. Do not edit them; coverage points
live in coverage/ and attach via `bind`.
