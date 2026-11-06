# Triki BLE client

Minimal Python client for the Żabka "Triki" BLE device (nRF52810 + LSM6DSL IMU). Streams gyro/accelerometer data and button state, and controls the LED.

Findings below were verified on a real device. They come from the reverse-engineering notes in `.tmp/` (`triki.md` and the `zabka-triki-hardware` repo), where the two sources disagreed in places.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python triki.py            # print live samples for 10 s
.venv/bin/python triki.py --led      # blink the LED first
```

```python
t = await Triki.connect()
await t.set_led(True)
async for s in t.samples():   # s.button, s.gyro (deg/s), s.accel (g)
    ...
await t.close()
```

On macOS the terminal needs Bluetooth permission. Close the Żappka app and TrikiScope first: the device accepts only one connection.

## Protocol

**Device:** advertises as `Triki <number>`. `TrikiDfu*` means firmware-update mode.

| Role | UUID | Properties |
| --- | --- | --- |
| Service (Nordic UART) | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | |
| RX | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | write, write-without-response |
| TX | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | notify |
| LED | `6e400004-b5a3-f393-e0a9-e50e24dcca9e` | write, read |

There is also a standard Battery service (`0x180F`), not used here.

### Starting the stream

1. Subscribe to notifications on TX.
2. Write `20 10 00 D0 07 68 00 03` to RX.

The device then sends a 5-byte ack (`21 00 00 00 00`) followed by the IMU stream. The `01 00` prefix and the `34` byte shown in `triki.md` are not needed (`34` was not tested).

### Stream format

Notifications are 20- and 16-byte fragments of one continuous stream, so reassemble them before decoding. Each frame is 14 bytes:

```text
22 | button | gyroX | gyroY | gyroZ | accelX | accelY | accelZ
```

All values are signed int16, little-endian. Rate is about 102.5 frames per second.

| Field | Meaning | Scale |
| --- | --- | --- |
| byte 1 | button: `0` released, `1` pressed | |
| gyro | angular rate | ÷ 131 gives deg/s |
| accel | acceleration | ÷ 2048 gives g |

At rest the accelerometer magnitude is about 1.00 g and the gyro reads under 1 deg/s.

### LED

Write `01` (on) or `00` (off) to the LED characteristic with `response=True`. Reading it returns the last value written.

## Do not

Never write `0x42` to RX. It reboots the device into DFU (firmware update) mode (see `.tmp/zabka-triki-hardware/dfu_trigger.py`).

## Not verified

- Axis sign conventions of gyro vs. accelerometer (matters for sensor fusion).
- The `34` init variant from `triki.md`.
- Which button value corresponds to a press was inferred from changes during a run, not from a clean isolated press.
