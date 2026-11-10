"""Strict Vietnamese grammar; unknown region names never select a fallback."""
from dataclasses import dataclass
import re
import unicodedata


def normalize(text):
    text = unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return ' '.join(re.sub(r'[^a-z0-9 ]', ' ', text).split())


@dataclass(frozen=True)
class Command:
    kind: str
    route: tuple = ()


class CommandError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class CommandParser:
    def __init__(self, regions):
        self.aliases = {}
        for region in regions:
            for alias in [region['id'], region['name'], *region.get('aliases', [])]:
                key = normalize(alias)
                if not key or (key in self.aliases and self.aliases[key] != region['id']):
                    raise ValueError('Empty or ambiguous region alias: ' + alias)
                self.aliases[key] = region['id']

    def resolve(self, name):
        if name not in self.aliases:
            raise CommandError('UNKNOWN_REGION', f'Không tồn tại khu vực: {name}')
        return self.aliases[name]

    def parse(self, text):
        t = normalize(text)
        if t in ('dung', 'dung lai', 'dung robot', 'huy', 'huy dieu huong', 'stop'):
            return Command('stop')
        t = re.sub(r'^(?:robot )?(?:hay |vui long )?', '', t)
        route = re.fullmatch(r'(?:di chuyen|di) tu (.+?) (?:den|toi) (.+)', t)
        if route:
            return Command('navigate', tuple(self.resolve(v) for v in route.groups()))
        dest = re.fullmatch(r'(?:di|di chuyen) (?:den|toi) (.+)', t)
        if dest:
            return Command('navigate', (self.resolve(dest[1]),))
        raise CommandError('UNKNOWN_COMMAND', 'Không hiểu câu lệnh. Ví dụ: Đi đến khu vực A.')
