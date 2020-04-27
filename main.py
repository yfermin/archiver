from dataclasses import dataclass
from sys import argv
from pathlib import Path
from functools import partial
from gdrive import GoogleDriveFile, MimeType, Service, walk_tree

BASE_PATH = Path("/tmp/buf/archiver/out")

DEFAULT_OUT = Path("/tmp/buf/archiver/out")


@dataclass(frozen=True)
class MimeTypeExtension:
    mime: str
    ext: str


DOC_EXPORT_MIME_TYPE_EXTS = [
    MimeTypeExtension(mime="text/plain", ext="txt"),
    MimeTypeExtension(mime="application/rtf", ext="rtf"),
    MimeTypeExtension(mime="application/pdf", ext="pdf"),
]


def archive_file(srv: Service, base_out_directory: Path, file: GoogleDriveFile):
    if file.mime != MimeType.Document:
        return

    out_directory = Path(base_out_directory / f"{file.path}/{file.name}")
    out_directory.mkdir(parents=True, exist_ok=True)

    for mime_type_ext in DOC_EXPORT_MIME_TYPE_EXTS:
        file_name = f"{file.path}/{file.name}.{mime_type_ext.ext}"
        bytes_steam = srv.export_file(
            file_name=file_name, file_id=file.id, mime_type=mime_type_ext.mime)
        Path(out_directory /
             f"{file.name}.{mime_type_ext.ext}").write_bytes(bytes_steam.getbuffer())


def download_file(srv: Service, file: GoogleDriveFile, mime_type_ext: MimeTypeExtension):
    if file.mime != MimeType.Document:
        return
    base_path = Path(BASE_PATH / file.path)
    base_path.mkdir(parents=True, exist_ok=True)
    file_name = f"{file.path}/{file.name}"
    bytes_steam = srv.export_file(
        file_name=file_name, file_id=file.id, mime_type=mime_type_ext.mime)
    Path(base_path /
         f"{file.name}.{mime_type_ext.ext}").write_bytes(bytes_steam.getbuffer())


if __name__ == "__main__":
    out_directory = DEFAULT_OUT
    if len(argv) > 1:
        out_directory = Path(argv[1])
    out_directory.mkdir(parents=True, exist_ok=True)

    srv = Service()
    srv.connect()
    root = srv.get_directory(root_name="My Writings")

    def callback(file: GoogleDriveFile):
        archive_file(srv=srv, base_out_directory=out_directory, file=file)

    walk_tree(root=root, callback=callback)
