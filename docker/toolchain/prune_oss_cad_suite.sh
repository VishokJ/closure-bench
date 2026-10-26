#!/bin/bash
# Prune an extracted OSS CAD Suite release (/opt/oss-cad-suite, 2.3 GB) to what
# the formal measurement needs: Yosys, SymbiYosys, Yices 2, Bitwuzla, their
# bundled Python and the shared libraries those programs load (~440 MB).
# Run in the Dockerfile's builder stage only.
set -euo pipefail
S=/opt/oss-cad-suite
# The arm64 release also ships an x86-64 loader: pick this machine's.
case "$(uname -m)" in
  x86_64)  LD=$S/lib/ld-linux-x86-64.so.2 ;;
  aarch64) LD=$S/lib/ld-linux-aarch64.so.1 ;;
  *) echo "unsupported machine $(uname -m)" >&2; exit 1 ;;
esac
KEEP_BIN="yosys yosys-abc yosys-smtbmc yosys-witness yosys-config sby tabbypy3 yices yices-smt2 bitwuzla"
mkdir -p /tmp/keep/bin /tmp/keep/libexec /tmp/keep/lib /tmp/keep/share
for b in $KEEP_BIN; do
  cp -a $S/bin/$b /tmp/keep/bin/
  # every libexec program the wrapper starts (e.g. tabbypy3 -> python3.11)
  for x in $(grep -ao 'libexec/[A-Za-z0-9_.+-]*' $S/bin/$b | sort -u); do
    if [ -e "$S/$x" ]; then cp -a "$S/$x" /tmp/keep/libexec/; fi
  done
done
# shared libraries: closure over the kept executables and python's extension modules
libs=$( { for f in /tmp/keep/libexec/* $S/lib/python3.11/lib-dynload/*.so $S/lib/libpython3*.so*; do
            LD_LIBRARY_PATH=$S/lib "$LD" --list "$f" 2>/dev/null || true; done; } \
        | awk '{print $3}' | grep "^$S/lib/" | sort -u)
for l in $libs; do cp -aL "$l" /tmp/keep/lib/; done
cp -a "$LD" $S/lib/libpython3*.so* /tmp/keep/lib/
cp -a $S/lib/python3.11 /tmp/keep/lib/
cp -a $S/share/yosys /tmp/keep/share/
cp -a $S/license /tmp/keep/ 2>/dev/null || true
rm -rf $S && mv /tmp/keep $S
