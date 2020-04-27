import json
import os
import pickle
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pathlib import Path
from typing import Callable, List, Optional

BASE_PATH = Path.home() / ".archiver"
TOKEN_STORAGE_FILE = str(BASE_PATH / "token.pickle")
CLIENT_SECRETS_FILE = str(BASE_PATH / "credentials.json")
SCOPES = [
    'https://www.googleapis.com/auth/drive.metadata.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]


@dataclass(frozen=True)
class GoogleDriveFile:
    id: str
    name: str
    mime: 'MimeType'
    path: str
    # https://www.python.org/dev/peps/pep-0484/#forward-references
    children: List['GoogleDriveFile']


class MimeType(Enum):
    Folder = 0
    Document = 1
    OtherFile = 2


@dataclass(frozen=True)
class _GoogleApiFile:
    id: str
    name: str
    mime_type: str
    parents: [str]


class Service:
    def __init__(self):
        self._creds = None
        self._service = None

    def connect(self):
        self._creds = _get_creds()
        self._service = build('drive', 'v3', credentials=self._creds)

    def get_directory(self, root_name: str) -> GoogleDriveFile:
        files = []
        page_token = None
        while True:
            response = self._service.files().list(q="trashed=false",
                                                  spaces='drive',
                                                  fields='nextPageToken, files(id, name, mimeType, parents)',
                                                  pageToken=page_token).execute()
            for file in response.get('files', []):
                files.append(_GoogleApiFile(
                    id=file['id'],
                    name=file['name'],
                    mime_type=file['mimeType'],
                    parents=file.get('parents', [])
                ))
            page_token = response.get('nextPageToken', None)
            if page_token is None:
                break

        root = next((file for file in files if file.name == root_name), None)
        if not root:
            print(f"Couldn't find root directory: {root_name}")
            exit(1)

        return _build_tree(files=files, root=root)

    def export_file(self, file_name: str, file_id: str, mime_type: str) -> BytesIO:
        request = self._service.files().export_media(fileId=file_id,
                                                     mimeType=mime_type)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        print(f"Downloading {file_name}")
        while done is False:
            _, done = downloader.next_chunk()
        return fh



def walk_tree(root: GoogleDriveFile, callback: Callable[[GoogleDriveFile], None]):
    callback(root)
    for child in root.children:
        walk_tree(root=child, callback=callback)


def _get_creds() -> Credentials:
    # Make $HOME/.archiver on first-time use.
    BASE_PATH.mkdir(parents=True, exist_ok=True)

    creds = None
    if os.path.exists(TOKEN_STORAGE_FILE):
        with open(TOKEN_STORAGE_FILE, 'rb') as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            _check_secrets_file()
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(TOKEN_STORAGE_FILE, 'wb') as token:
            pickle.dump(creds, token)

    return creds


def _build_tree(files: List[_GoogleApiFile], root: _GoogleApiFile) -> GoogleDriveFile:
    def _helper(files: List[_GoogleApiFile], path: str, parent: str) -> List[GoogleDriveFile]:
        out_files = []
        for file in files:
            if parent in file.parents:
                mime_type = _parse_mime_type(file.mime_type)
                if mime_type == MimeType.OtherFile:
                    continue

                children = []
                if mime_type == MimeType.Folder:
                    children = _helper(
                        files=files, path=f"{path}/{file.name}", parent=file.id)
                out_files.append(GoogleDriveFile(
                    id=file.id, name=file.name, mime=mime_type, path=path, children=children))
        return out_files
    return GoogleDriveFile(id=root.id, name=root.name, mime=MimeType.Folder, path="", children=_helper(files=files, path=root.name, parent=root.id))


def _parse_mime_type(mime_type: str) -> MimeType:
    if mime_type == "application/vnd.google-apps.folder":
        return MimeType.Folder
    elif mime_type == "application/vnd.google-apps.document":
        return MimeType.Document
    return MimeType.OtherFile


def _check_secrets_file():
    if not Path(CLIENT_SECRETS_FILE).exists():
        print(f"Client secrets not found. Add them to {CLIENT_SECRETS_FILE}")
        exit(1)
