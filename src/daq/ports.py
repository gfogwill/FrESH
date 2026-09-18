#!/usr/bin/env python3
"""Show the serial ports on this machine and which one the chiller will use.

    python -m src.daq.ports

Run it on the machine that is misbehaving. It prints every serial port with
its description and hardware id, what the configuration says, and which port
the chiller code would pick -- without opening anything.
"""

import logging
import sys

from src.config import get_config
from src.daq.chillers import (CHILLERS, configured_port, find_chiller_port,
                              list_serial_ports)


def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')

    print("Serial ports on this machine")
    print("-" * 72)
    ports = list_serial_ports()
    if not ports:
        print("  (none found -- is the adapter plugged in, and do you have "
              "permission to read /dev/ttyUSB*?)")
    for device, description, hwid in ports:
        print(f"  {device:<20} {description}")
        print(f"  {'':<20} {hwid}")

    try:
        config = get_config()
    except FileNotFoundError as e:
        print(f"\nNo configuration: {e}")
        return 1

    model = config['CHILLER']['MODEL'].strip().upper()
    adam_port = configured_port(config, 'SERIAL')
    chiller_port = configured_port(config, 'CHILLER')

    print("\nConfiguration")
    print("-" * 72)
    print(f"  chiller model            {model}")
    print(f"  [SERIAL] PORT  (ADAM)    {adam_port or '(unset)'}")
    print(f"  [CHILLER] PORT           {chiller_port or '(unset -- will be guessed)'}")

    chiller_class = CHILLERS.get(model)
    if chiller_class is None:
        print(f"\n  Unknown model {model}. Supported: {', '.join(sorted(CHILLERS))}")
        return 1

    reserved = chiller_class(config).reserved_ports()

    print("\nWhat the chiller code would do")
    print("-" * 72)
    chosen = find_chiller_port(config, exclude=reserved)
    print(f"\n  -> chiller on {chosen or 'NOTHING -- it would fail to connect'}")

    if chosen and chosen in {p for p in reserved if p}:
        print("  !! that is also the ADAM's port; set [CHILLER] PORT")
        return 1

    if chosen is None:
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
