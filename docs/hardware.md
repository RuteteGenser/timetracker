# Hardware: parts and wiring

Prices are rough estimates (USD, 2026) from memory, not checked live. Check
current prices and stock before ordering.

## Shopping list (best value, nothing fancy)

| Part | Why | ~Price |
|---|---|---|
| Raspberry Pi 5, 2 GB or 4 GB | Has a built-in clock (RTC); a Pi 4 needs an extra clock module | $50-60 |
| Official Pi 5 power supply (27 W USB-C) | The Pi 5 is picky about power; skip cheap supplies | $12 |
| Official RTC battery for Pi 5 | Keeps the time while unplugged | $5 |
| Raspberry Pi Touch Display 2 (7") | Official, connects with one ribbon cable, no extra drivers. Check the box lists a cable for the Pi 5 | $60 |
| microSD card, 32 GB, "high endurance" type | You will pull the plug a lot; endurance cards cope better | $10-12 |
| KY-040 rotary encoder module (often sold in packs of 5) | Cheap, has header pins, so no soldering | $2-8 |
| 30 mm arcade push button with quick-connect wires ending in female Dupont | Big, easy to hit without looking | $3-6 |
| Female-to-female Dupont jumper wires (40 pcs) | All connections | $4 |
| Tablet / photo-frame stand | Holds the screen upright, no 3D printing | $8-10 |

Total: about $150-170. Only a Pi 5 is assumed; for a Pi 4 add a DS3231 clock
module (about $3) and let the project know, and its wiring will be added.

Not needed: a power button (it boots when plugged in), a case, a cooler.

## Wiring (physical pin numbers, Pi 5 and Pi 4 are identical)

Hold the Pi with the header at the top edge and the SD slot facing away from you;
odd pins are the inner row, even pins the outer row. All pins used here are on
the same side of the header, away from the display's power pins.

| From | To Pi pin | Pi function |
|---|---|---|
| Encoder CLK | 11 | GPIO17 |
| Encoder DT | 13 | GPIO27 |
| Encoder GND | 14 | Ground |
| Encoder `+` and SW | not connected | |
| Button, one wire | 15 | GPIO22 |
| Button, other wire | 9 | Ground |

The Touch Display 2 takes its power from pins 2 (5 V) and 6 (Ground) through its
own supplied cable; its touch signals travel in the ribbon cable, so nothing
above clashes with it. The inputs use the Pi's internal pull-up resistors, so
no extra resistors are needed.

Both pin numbers are configurable in `config.toml` (`[gpio]`).

## Clock (Pi 5)

Plug the RTC battery into the Pi 5's dedicated battery connector (see the
official RTC battery instructions for its location). To let the Pi recharge it, add this line to `/boot/firmware/config.txt`:

```
dtparam=rtc_bbat_vchg=3000000
```

(The setup guide, milestone 6, will include this step.)

## Setting the clock from the app (Pi only)

Settings > Date & time sets the real clock. A normal user may not do that, so on the Pi the app calls a
tiny root-owned helper through `sudo`. It is installed by the setup guide (milestone 6); the design is:

- `/usr/local/bin/timetracker-set-time EPOCH`: checks that `EPOCH` is a plain number in a sane range, runs
  `timedatectl set-time` with it and then `hwclock --systohc` so the Pi 5's RTC keeps the new time.
- a sudoers line that allows the app's user to run *only that script* without a password.
- `driver = "system"` under `[clock]` in `config.toml`. On a PC the default `"offset"` driver leaves the
  computer's clock alone and the app keeps its own offset.

## Not yet verified

Nothing has been tested on real hardware yet; GPIO input and kiosk boot arrive
in milestone 5. Pin choices were checked against the standard 40-pin header
layout, they still need rechecking on a real board during milestone 5.
