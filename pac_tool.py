#!/usr/bin/env python3
import struct
import json
import zlib
import argparse
import os
import shutil
from pathlib import Path
from typing import List, Union, BinaryIO

# Константы
ENTRY_NAME_SIZE = 56


class ResName:
    """Variable-length SHIFT-JIS-encoded resource name"""

    def __init__(self, value: str = ""):
        self.value = value

    @classmethod
    def from_bytes(cls, data: bytes) -> "ResName":
        """Read from binary data"""
        length = struct.unpack("<I", data[:4])[0]
        sj_bytes = data[4 : 4 + length]
        try:
            value = sj_bytes.decode("shift_jis")
        except UnicodeDecodeError:
            value = sj_bytes.decode("shift_jis", errors="replace")
        return cls(value)

    def to_bytes(self) -> bytes:
        """Convert to binary representation"""
        try:
            encoded = self.value.encode("shift_jis")
        except UnicodeEncodeError:
            # Fallback: replace problematic characters
            encoded = self.value.encode("shift_jis", errors="replace")

        length = len(encoded)
        return struct.pack("<I", length) + encoded

    def to_json(self) -> str:
        return self.value

    @classmethod
    def from_json(cls, value: str) -> "ResName":
        return cls(value)


class TtpFrame:
    """Frame of animation"""

    def __init__(self):
        self.sprite_name = ResName()
        self.se_name = ResName()
        self.textbox_name = ResName()
        self.delay_ms = 0
        self.x_offset_textbox = 0
        self.y_offset_textbox = 0
        self.x_offset = 0
        self.y_offset = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> "TtpFrame":
        """Read from binary data"""
        frame = cls()
        pos = 0

        # Read resource names
        frame.sprite_name = ResName.from_bytes(data[pos:])
        pos += 4 + len(frame.sprite_name.value.encode("shift_jis"))

        frame.se_name = ResName.from_bytes(data[pos:])
        pos += 4 + len(frame.se_name.value.encode("shift_jis"))

        frame.textbox_name = ResName.from_bytes(data[pos:])
        pos += 4 + len(frame.textbox_name.value.encode("shift_jis"))

        # Read numeric values
        values = struct.unpack("<5I", data[pos : pos + 20])
        frame.delay_ms = values[0]
        frame.x_offset_textbox = values[1]
        frame.y_offset_textbox = values[2]
        frame.x_offset = values[3]
        frame.y_offset = values[4]

        return frame

    def to_bytes(self) -> bytes:
        """Convert to binary representation"""
        data = b""
        data += self.sprite_name.to_bytes()
        data += self.se_name.to_bytes()
        data += self.textbox_name.to_bytes()
        data += struct.pack(
            "<5I",
            self.delay_ms,
            self.x_offset_textbox,
            self.y_offset_textbox,
            self.x_offset,
            self.y_offset,
        )
        return data

    def to_dict(self) -> dict:
        return {
            "sprite_name": self.sprite_name.to_json(),
            "se_name": self.se_name.to_json(),
            "textbox_name": self.textbox_name.to_json(),
            "delay_ms": self.delay_ms,
            "x_offset_textbox": self.x_offset_textbox,
            "y_offset_textbox": self.y_offset_textbox,
            "x_offset": self.x_offset,
            "y_offset": self.y_offset,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TtpFrame":
        frame = cls()
        frame.sprite_name = ResName.from_json(data["sprite_name"])
        frame.se_name = ResName.from_json(data["se_name"])
        frame.textbox_name = ResName.from_json(data["textbox_name"])
        frame.delay_ms = data["delay_ms"]
        frame.x_offset_textbox = data["x_offset_textbox"]
        frame.y_offset_textbox = data["y_offset_textbox"]
        frame.x_offset = data["x_offset"]
        frame.y_offset = data["y_offset"]
        return frame


class TtpFile:
    """Encoded animation"""

    def __init__(self):
        self.maybe_ttp_type = 0
        self.frame_count = 0
        self.window_width = 0
        self.window_height = 0
        self.frames = []
        self.onetime_wakeup_dont_play_sound = None

    @classmethod
    def from_bytes(cls, data: bytes) -> "TtpFile":
        """Read from binary data"""
        ttp = cls()
        pos = 0

        # Read header
        header = struct.unpack("<4I", data[pos : pos + 16])
        ttp.maybe_ttp_type = header[0]
        ttp.frame_count = header[1]
        ttp.window_width = header[2]
        ttp.window_height = header[3]
        pos += 16

        # Read frames
        ttp.frames = []
        for _ in range(ttp.frame_count):
            frame = TtpFrame.from_bytes(data[pos:])
            ttp.frames.append(frame)
            pos += 4 + len(frame.sprite_name.value.encode("shift_jis"))
            pos += 4 + len(frame.se_name.value.encode("shift_jis"))
            pos += 4 + len(frame.textbox_name.value.encode("shift_jis"))
            pos += 20

        # Read optional flag
        if ttp.maybe_ttp_type == 3:
            if pos < len(data):
                ttp.onetime_wakeup_dont_play_sound = struct.unpack(
                    "<B", data[pos : pos + 1]
                )[0]

        return ttp

    def to_bytes(self) -> bytes:
        """Convert to binary representation"""
        data = struct.pack(
            "<4I",
            self.maybe_ttp_type,
            self.frame_count,
            self.window_width,
            self.window_height,
        )

        for frame in self.frames:
            data += frame.to_bytes()

        if self.maybe_ttp_type == 3 and self.onetime_wakeup_dont_play_sound is not None:
            data += struct.pack("<B", self.onetime_wakeup_dont_play_sound)

        return data

    def to_dict(self) -> dict:
        result = {
            "maybe_ttp_type": self.maybe_ttp_type,
            "frame_count": self.frame_count,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "frames": [frame.to_dict() for frame in self.frames],
        }

        if self.onetime_wakeup_dont_play_sound is not None:
            result[
                "onetime_wakeup_dont_play_sound"
            ] = self.onetime_wakeup_dont_play_sound

        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TtpFile":
        ttp = cls()
        ttp.maybe_ttp_type = data["maybe_ttp_type"]
        ttp.frame_count = data["frame_count"]
        ttp.window_width = data["window_width"]
        ttp.window_height = data["window_height"]
        ttp.frames = [TtpFrame.from_dict(frame) for frame in data["frames"]]
        ttp.onetime_wakeup_dont_play_sound = data.get("onetime_wakeup_dont_play_sound")
        return ttp


class PacFile:
    """Representation of files found in archive"""

    BMZ_HEADER_SIZE = 8

    def __init__(self):
        self.file_type = "other"
        self.data = b""
        self.uncompressed_size = 0

    @classmethod
    def from_bytes(cls, data: bytes, size: int) -> "PacFile":
        """Read from binary data"""
        pac_file = cls()

        if data.startswith(b"ZLC3"):
            # BMZ file
            pac_file.file_type = "bmz"
            pac_file.uncompressed_size = struct.unpack("<I", data[4:8])[0]
            pac_file.data = data[8:size]
        elif data[:4] == b"\x00\x00\x00\x00" or True:  # Assume TTP based on structure
            try:
                # Try to parse as TTP
                ttp = TtpFile.from_bytes(data[:size])
                pac_file.file_type = "ttp"
                pac_file.data = data[:size]
            except:
                pac_file.file_type = "other"
                pac_file.data = data[:size]
        else:
            pac_file.file_type = "other"
            pac_file.data = data[:size]

        return pac_file

    def converted_data(self) -> bytes:
        """Get converted data for extraction"""
        if self.file_type == "bmz":
            try:
                return zlib.decompress(self.data)
            except zlib.error as e:
                raise ValueError(f"Failed to decompress BMZ: {e}")
        elif self.file_type == "ttp":
            ttp = TtpFile.from_bytes(self.data)
            return json.dumps(ttp.to_dict(), indent=2, ensure_ascii=False).encode(
                "utf-8"
            )
        else:
            return self.data

    def to_bytes(self) -> bytes:
        """Convert to binary representation for packing"""
        if self.file_type == "bmz":
            header = b"ZLC3" + struct.pack("<I", self.uncompressed_size)
            return header + self.data
        else:
            return self.data

    @staticmethod
    def original_ext(conv_ext: str) -> str:
        """Get original (packed) extension"""
        return {"bmp": "bmz", "json": "ttp"}.get(conv_ext, conv_ext)

    @staticmethod
    def converted_ext(orig_ext: str) -> str:
        """Get converted (extracted) extension"""
        return {"bmz": "bmp", "ttp": "json"}.get(orig_ext, orig_ext)

    @classmethod
    def convert_back(cls, data: bytes, conv_extension: str) -> "PacFile":
        """Build file from raw data for packing"""
        pac_file = cls()

        if conv_extension == "bmp":
            pac_file.file_type = "bmz"
            pac_file.uncompressed_size = len(data)
            pac_file.data = zlib.compress(data)
        elif conv_extension == "json":
            pac_file.file_type = "ttp"
            ttp_dict = json.loads(data.decode("utf-8"))
            ttp = TtpFile.from_dict(ttp_dict)
            pac_file.data = ttp.to_bytes()
        else:
            pac_file.file_type = "other"
            pac_file.data = data

        return pac_file


class PacEntry:
    """Struct for reading archive entries"""

    def __init__(self):
        self.offset = 0
        self.size = 0
        self.name = ""
        self.file_data = PacFile()

    @classmethod
    def from_file(cls, f: BinaryIO) -> "PacEntry":
        """Read entry from file"""
        entry = cls()

        # Read offset and size
        offset_size_data = f.read(8)
        if len(offset_size_data) < 8:
            raise EOFError("Unexpected end of file")

        entry.offset, entry.size = struct.unpack("<II", offset_size_data)

        # Read name
        name_data = f.read(ENTRY_NAME_SIZE)
        try:
            # Find null terminator
            null_pos = name_data.find(b"\x00")
            if null_pos != -1:
                name_data = name_data[:null_pos]
            entry.name = name_data.decode("shift_jis")
        except UnicodeDecodeError:
            entry.name = name_data.decode("shift_jis", errors="replace")

        # Store current position and read file data
        current_pos = f.tell()
        f.seek(entry.offset)
        file_bytes = f.read(entry.size)
        entry.file_data = PacFile.from_bytes(file_bytes, entry.size)
        f.seek(current_pos)

        return entry

    def to_bytes(self) -> bytes:
        """Convert to binary representation for packing"""
        name_encoded = self.name.encode("shift_jis", errors="replace")[
            : ENTRY_NAME_SIZE - 1
        ]
        name_padded = name_encoded + b"\x00" * (ENTRY_NAME_SIZE - len(name_encoded))

        return struct.pack("<II", self.offset, self.size) + name_padded


class PacArchive:
    """Struct for reading Pac archive"""

    def __init__(self):
        self.entries_count = 0
        self.entries = []

    @classmethod
    def from_file(cls, filename: str) -> "PacArchive":
        """Read archive from file"""
        archive = cls()

        with open(filename, "rb") as f:
            # Read entries count
            entries_count_data = f.read(4)
            if len(entries_count_data) < 4:
                raise ValueError("Invalid archive file")

            archive.entries_count = struct.unpack("<I", entries_count_data)[0]

            # Read entries
            archive.entries = []
            for _ in range(archive.entries_count):
                entry = PacEntry.from_file(f)
                archive.entries.append(entry)

        return archive

    def extract_all(self, out_dir: str):
        """Extract and convert all files"""
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        for entry in self.entries:
            try:
                converted_data = entry.file_data.converted_data()
                orig_ext = Path(entry.name).suffix[1:]  # Remove dot
                conv_ext = PacFile.converted_ext(orig_ext)

                output_path = out_path / f"{Path(entry.name).stem}.{conv_ext}"

                with open(output_path, "wb") as f:
                    f.write(converted_data)

                print(f"Extracted: {output_path}")
            except Exception as e:
                print(f"Error extracting {entry.name}: {e}")

    def list_files(self):
        """List all files in archive"""
        print(f"{'Index':<6}{'Size':<10}{'Info':<48}{'Name'}")
        print("-" * 80)

        for idx, entry in enumerate(self.entries):
            info = ""
            if entry.file_data.file_type == "bmz":
                info = f"bmz uncompressed size: {entry.file_data.uncompressed_size}"
            elif entry.file_data.file_type == "ttp":
                try:
                    ttp = TtpFile.from_bytes(entry.file_data.data)
                    info = f"ttp type?: {ttp.maybe_ttp_type:<3} w: {ttp.window_width:<4} h: {ttp.window_height:<4} frames: {ttp.frame_count}"
                except:
                    info = "ttp (parse error)"
            else:
                info = "other file"

            print(f"{idx:<6}{entry.size:<10}{info:<48}{entry.name}")


class PacArchiveBuilder:
    """Builder for Pac archives"""

    def __init__(self):
        self.entries = []

    def add_entry(self, file_data: PacFile, name: str):
        """Add new entry to archive"""
        if len(name.encode("shift_jis")) >= ENTRY_NAME_SIZE:
            raise ValueError(f"Too long entry name: {name}")

        entry = PacEntry()
        entry.name = name
        entry.file_data = file_data
        self.entries.append(entry)

    def pack(self, out_path: str):
        """Pack all entries to archive"""
        with open(out_path, "wb") as f:
            # Write entries count
            f.write(struct.pack("<I", len(self.entries)))

            # Calculate offsets and write header
            current_offset = 4 + PacEntry.ENTRY_HEADER_SIZE * len(self.entries)

            # First pass: write headers with temporary offsets
            headers = []
            for entry in self.entries:
                entry.offset = current_offset
                file_bytes = entry.file_data.to_bytes()
                entry.size = len(file_bytes)
                headers.append(entry.to_bytes())
                current_offset += entry.size

            # Write all headers
            for header in headers:
                f.write(header)

            # Second pass: write file data
            for entry in self.entries:
                file_bytes = entry.file_data.to_bytes()
                f.write(file_bytes)


# Add constant to PacEntry class
PacEntry.ENTRY_HEADER_SIZE = 8 + ENTRY_NAME_SIZE


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description="Utility for extracting and packing pac archives of ひぐらしのなく頃に礼 デスクトップアクセサリー",
        epilog="Example: python pac_tool.py extract game.pac extracted_files/",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Extract command
    extract_parser = subparsers.add_parser(
        "extract", aliases=["x"], help="Extract all files from arc to out_dir"
    )
    extract_parser.add_argument("arc", help=".pac archive")
    extract_parser.add_argument(
        "out_dir",
        help="out folder, will be created if not exists, all contents will be REMOVED if exists",
    )

    # List command
    list_parser = subparsers.add_parser(
        "list", aliases=["l"], help="List all files in archive"
    )
    list_parser.add_argument("arc", help=".pac archive")

    # Pack command
    pack_parser = subparsers.add_parser(
        "pack", aliases=["p"], help="Pack directory into archive"
    )
    pack_parser.add_argument("out_arc", help="Result will be saved to this file")
    pack_parser.add_argument("src_dir", help="Build archive from this directory")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command in ["extract", "x"]:
            # Remove existing directory
            out_path = Path(args.out_dir)
            if out_path.exists():
                if out_path.is_dir():
                    shutil.rmtree(out_path)
                else:
                    print(f"Error: {args.out_dir} is not a directory")
                    return

            # Extract archive
            archive = PacArchive.from_file(args.arc)
            archive.extract_all(args.out_dir)
            print("All files extracted successfully")

        elif args.command in ["list", "l"]:
            # List archive contents
            archive = PacArchive.from_file(args.arc)
            archive.list_files()

        elif args.command in ["pack", "p"]:
            # Pack directory
            builder = PacArchiveBuilder()
            src_path = Path(args.src_dir)

            if not src_path.exists() or not src_path.is_dir():
                print(f"Error: {args.src_dir} is not a directory")
                return

            for file_path in src_path.iterdir():
                if file_path.is_file():
                    try:
                        with open(file_path, "rb") as f:
                            file_data = f.read()

                        conv_ext = file_path.suffix[1:]  # Remove dot
                        pac_file = PacFile.convert_back(file_data, conv_ext)

                        orig_ext = PacFile.original_ext(conv_ext)
                        new_name = file_path.with_suffix(f".{orig_ext}").name

                        builder.add_entry(pac_file, new_name)
                        print(f"Added: {new_name}")

                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")

            builder.pack(args.out_arc)
            print("All files packed successfully")

    except Exception as e:
        print(f"Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
