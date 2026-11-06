"""Minimal Triki BLE client: stream IMU + button, control LED.

    pip install bleak
    python triki.py            # print live samples for 10 s
    python triki.py --led      # blink LED, then print samples

Never write 0x42 to the RX characteristic: it reboots the device into DFU mode.
"""
import argparse
import asyncio
import struct
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from bleak import BleakClient, BleakScanner

RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"   # write
TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"   # notify (stream)
LED = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"  # write (response=True) / read

INIT = bytes([0x20, 0x10, 0x00, 0xD0, 0x07, 0x68, 0x00, 0x03])
FRAME_LEN = 14
GYRO_SCALE = 131.0    # LSB per deg/s
ACCEL_SCALE = 2048.0  # LSB per g


@dataclass
class Sample:
    button: bool
    gyro: tuple   # deg/s (x, y, z)
    accel: tuple  # g (x, y, z)


def parse_frames(buf: bytes):
    """Split a reassembled byte stream into Samples; returns (samples, leftover)."""
    out = []
    while len(buf) >= FRAME_LEN:
        if buf[0] != 0x22:           # resync on header
            buf = buf[1:]
            continue
        v = struct.unpack_from("<6h", buf, 2)
        out.append(Sample(
            button=buf[1] == 1,
            gyro=tuple(x / GYRO_SCALE for x in v[:3]),
            accel=tuple(x / ACCEL_SCALE for x in v[3:]),
        ))
        buf = buf[FRAME_LEN:]
    return out, buf


async def find_triki(timeout: float = 8):
    devs = await BleakScanner.discover(timeout=timeout, return_adv=True)
    for d, a in devs.values():
        name = d.name or a.local_name or ""
        if name.startswith("Triki") and not name.startswith("TrikiDfu"):
            return d
    return None


class Triki:
    def __init__(self, client: BleakClient):
        self.client = client
        self._q: asyncio.Queue = asyncio.Queue()
        self._buf = b""

    @classmethod
    async def connect(cls, device=None):
        device = device or await find_triki()
        if device is None:
            raise RuntimeError("no Triki found (awake? Żappka/TrikiScope closed?)")
        client = BleakClient(device, timeout=20)
        await client.connect()
        t = cls(client)
        await client.start_notify(TX, t._on_notify)
        await client.write_gatt_char(RX, INIT, response=False)
        return t

    def _on_notify(self, _, data: bytearray):
        # Notifications are MTU-sized fragments of one stream (plus a 5-byte
        # `21 00 00 00 00` ack at start): reassemble before parsing.
        if len(data) == 5 and data[0] == 0x21:
            return
        samples, self._buf = parse_frames(self._buf + bytes(data))
        for s in samples:
            self._q.put_nowait(s)

    async def samples(self) -> AsyncIterator[Sample]:
        while True:
            yield await self._q.get()

    async def set_led(self, on: bool):
        await self.client.write_gatt_char(LED, bytes([1 if on else 0]), response=True)

    async def close(self):
        await self.client.disconnect()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10)
    ap.add_argument("--led", action="store_true", help="blink LED first")
    args = ap.parse_args()

    t = await Triki.connect()
    try:
        if args.led:
            for on in (True, False, True, False):
                await t.set_led(on)
                await asyncio.sleep(0.5)

        last: Optional[bool] = None
        n = 0
        end = asyncio.get_event_loop().time() + args.seconds
        async for s in t.samples():
            if s.button != last:  # edge detection
                print("button", "PRESSED" if s.button else "released")
                last = s.button
            n += 1
            if n % 10 == 0:
                print(f"gyro={tuple(round(x, 1) for x in s.gyro)} deg/s  "
                      f"accel={tuple(round(x, 2) for x in s.accel)} g")
            if asyncio.get_event_loop().time() > end:
                break
    finally:
        await t.close()


if __name__ == "__main__":
    asyncio.run(main())
