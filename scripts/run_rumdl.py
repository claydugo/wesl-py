import subprocess
import sys

if sys.platform != "darwin":
    sys.exit(subprocess.call(["rumdl", *sys.argv[1:]]))
