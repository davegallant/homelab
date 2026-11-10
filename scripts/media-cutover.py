#!/usr/bin/env python3
"""Validate staged HEVC candidates and promote them with a retained original."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class PipelineError(Exception):
    """Raised when a safety gate fails."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-show_chapters", "-of", "json", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise PipelineError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PipelineError(f"ffprobe returned invalid JSON for {path}") from exc


def _stream_signature(stream):
    tags = stream.get("tags", {})
    disposition = stream.get("disposition", {})
    return (
        stream.get("codec_type"),
        stream.get("codec_name"),
        stream.get("profile"),
        stream.get("width"),
        stream.get("height"),
        stream.get("pix_fmt"),
        stream.get("sample_rate"),
        stream.get("channels"),
        stream.get("channel_layout"),
        tags.get("language"),
        tags.get("title"),
        tuple(sorted((key, value) for key, value in disposition.items() if value)),
    )


def _seconds(value, field):
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise PipelineError(f"missing or invalid {field}") from exc


def validate_metadata(source_info, candidate_info, min_savings_percent=10.0):
    source_streams = source_info.get("streams", [])
    candidate_streams = candidate_info.get("streams", [])
    source_types = [stream.get("codec_type") for stream in source_streams]
    candidate_types = [stream.get("codec_type") for stream in candidate_streams]
    if sorted(source_types) != sorted(candidate_types):
        raise PipelineError("stream types/counts differ; candidate may have lost tracks")

    source_video = [stream for stream in source_streams if stream.get("codec_type") == "video"]
    candidate_video = [stream for stream in candidate_streams if stream.get("codec_type") == "video"]
    if not source_video or not candidate_video:
        raise PipelineError("source and candidate must contain video")
    if len(source_video) != len(candidate_video):
        raise PipelineError("video stream counts differ")
    for original, encoded in zip(source_video, candidate_video):
        if encoded.get("codec_name") != "hevc":
            raise PipelineError("candidate video is not HEVC")
        for field in ("width", "height", "pix_fmt", "avg_frame_rate", "color_range", "color_space", "color_transfer", "color_primaries"):
            if original.get(field) != encoded.get(field):
                raise PipelineError(f"video property changed: {field}")
        if _stream_signature(original)[9:] != _stream_signature(encoded)[9:]:
            raise PipelineError("video language, title, or dispositions changed")

    source_other = [stream for stream in source_streams if stream.get("codec_type") != "video"]
    candidate_other = [stream for stream in candidate_streams if stream.get("codec_type") != "video"]
    if [_stream_signature(stream) for stream in source_other] != [_stream_signature(stream) for stream in candidate_other]:
        raise PipelineError("non-video streams or their metadata changed")

    source_duration = _seconds(source_info.get("format", {}).get("duration"), "source duration")
    candidate_duration = _seconds(candidate_info.get("format", {}).get("duration"), "candidate duration")
    if abs(source_duration - candidate_duration) > 1.0:
        raise PipelineError("duration differs by more than one second")
    source_chapters = source_info.get("chapters", [])
    candidate_chapters = candidate_info.get("chapters", [])
    if len(source_chapters) != len(candidate_chapters):
        raise PipelineError("chapter counts differ")
    for source_chapter, candidate_chapter in zip(source_chapters, candidate_chapters):
        for field in ("start_time", "end_time"):
            if abs(_seconds(source_chapter.get(field), f"source chapter {field}") - _seconds(candidate_chapter.get(field), f"candidate chapter {field}")) > 1.0:
                raise PipelineError("chapter timing changed")
        if source_chapter.get("tags", {}) != candidate_chapter.get("tags", {}):
            raise PipelineError("chapter metadata changed")

    source_size = int(source_info.get("format", {}).get("size", 0))
    candidate_size = int(candidate_info.get("format", {}).get("size", 0))
    if source_size <= 0 or candidate_size <= 0:
        raise PipelineError("could not determine file sizes")
    savings_percent = (source_size - candidate_size) / source_size * 100
    if savings_percent < min_savings_percent:
        raise PipelineError(f"size savings {savings_percent:.1f}% are below the {min_savings_percent:.1f}% minimum")
    return {"source_size": source_size, "candidate_size": candidate_size, "savings_percent": round(savings_percent, 2)}


def decode_check(path):
    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(path), "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise PipelineError(f"full decode failed for candidate {path}: {result.stderr.strip()}")


def write_validation_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def validate(source, candidate, report_path, min_savings_percent=10.0):
    source = Path(source).resolve(strict=True)
    candidate = Path(candidate).resolve(strict=True)
    if source == candidate:
        raise PipelineError("source and candidate must be separate files")
    source_info = probe(source)
    candidate_info = probe(candidate)
    metrics = validate_metadata(source_info, candidate_info, min_savings_percent)
    decode_check(candidate)
    report = {
        "passed": True,
        "source": str(source),
        "candidate": str(candidate),
        "source_sha256": sha256(source),
        "candidate_sha256": sha256(candidate),
        "metrics": metrics,
        "visual_review_required": True,
    }
    write_validation_report(report_path, report)
    return report


def promote(source, candidate, report_path, backup):
    source = Path(source).absolute()
    candidate = Path(candidate).absolute()
    report_path = Path(report_path).resolve(strict=True)
    backup = Path(backup).absolute()
    if source == candidate:
        raise PipelineError("source and candidate must be separate files")
    if source.is_symlink() or candidate.is_symlink():
        raise PipelineError("symlinks are not eligible for promotion")
    source = source.resolve(strict=True)
    candidate = candidate.resolve(strict=True)
    backup = backup.parent.resolve() / backup.name
    if source.stat().st_nlink > 1:
        raise PipelineError("source is hard-linked; refusing to disrupt torrent/library links")
    if backup.exists():
        raise PipelineError(f"backup already exists: {backup}")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"cannot read validation report: {exc}") from exc
    if report.get("passed") is not True:
        raise PipelineError("validation report did not pass")
    if report.get("source") != str(source) or report.get("candidate") != str(candidate):
        raise PipelineError("validation report paths do not match these files")
    if report.get("source_sha256") != sha256(source):
        raise PipelineError("source changed after validation")
    if report.get("candidate_sha256") != sha256(candidate):
        raise PipelineError("candidate changed after validation")
    if backup.parent.resolve() != source.parent:
        raise PipelineError("original backup must be beside the source on the same filesystem")

    descriptor, candidate_temp_name = tempfile.mkstemp(prefix=f".{source.name}.candidate-", dir=source.parent)
    os.close(descriptor)
    candidate_temporary = Path(candidate_temp_name)
    descriptor, backup_temp_name = tempfile.mkstemp(prefix=f".{backup.name}.backup-", dir=source.parent)
    os.close(descriptor)
    backup_temporary = Path(backup_temp_name)
    try:
        shutil.copy2(candidate, candidate_temporary)
        if sha256(candidate_temporary) != report["candidate_sha256"]:
            raise PipelineError("candidate copy checksum mismatch")
        shutil.copy2(source, backup_temporary)
        if sha256(backup_temporary) != report["source_sha256"]:
            raise PipelineError("original backup checksum mismatch")
        os.link(backup_temporary, backup)
        backup_temporary.unlink()
        os.replace(candidate_temporary, source)
    except OSError as exc:
        raise PipelineError(f"promotion failed: {exc}") from exc
    finally:
        candidate_temporary.unlink(missing_ok=True)
        backup_temporary.unlink(missing_ok=True)
    return {"source": str(source), "backup": str(backup), "candidate": str(candidate)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate_parser = commands.add_parser("validate", help="probe, compare, and fully decode a candidate")
    validate_parser.add_argument("source")
    validate_parser.add_argument("candidate")
    validate_parser.add_argument("--report", required=True)
    validate_parser.add_argument("--minimum-savings-percent", type=float, default=10.0)
    promote_parser = commands.add_parser("promote", help="replace source while retaining its original beside it")
    promote_parser.add_argument("source")
    promote_parser.add_argument("candidate")
    promote_parser.add_argument("--report", required=True)
    promote_parser.add_argument("--backup", required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate":
            report = validate(args.source, args.candidate, args.report, args.minimum_savings_percent)
            print(json.dumps(report, indent=2))
        else:
            print(json.dumps(promote(args.source, args.candidate, args.report, args.backup), indent=2))
    except (PipelineError, OSError) as exc:
        print(f"media-cutover: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
