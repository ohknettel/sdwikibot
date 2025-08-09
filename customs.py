from typing import Any, TypedDict, Dict, NotRequired

class Host(TypedDict):
    name: str
    api_url: str
    main_url: str
    enabled: bool

class Continue(TypedDict):
    gapcontinue: str
    _continue: str

class RevisionContinue(TypedDict):
    gsroffset: int
    _continue: str

class Page(TypedDict):
    pageid: int
    ns: int
    title: str
    contentmodel: str
    pagelanguage: str
    pagelanguagehtmlcode: str
    pagelanguagedir: str
    touched: str
    lastrevid: int
    length: int
    fullurl: str
    editurl: str
    canonicalurl: str
    host: Host

class RevisionContent(TypedDict):
    contentmodel: str
    contentformat: str
    content: str

class Revision(TypedDict):
    slots: dict[str, RevisionContent]

class RevisionsPage(Page):
    revisions: list[Revision]

class RevisionsQuery(TypedDict):
    pages: list[RevisionsPage]

class Query(TypedDict):
    pages: Dict[str, Page]

class MediawikiGsearchResult(TypedDict):
    batchcomplete: NotRequired[str]
    _continue: NotRequired[Continue]
    query: Query

class MediawikiGsearchRevisionsResult(TypedDict):
    batchcomplete: NotRequired[bool]
    _continue: NotRequired[RevisionContinue]
    query: RevisionsQuery

class Parse(TypedDict):
    title: str
    pageid: int
    text: str

class MediawikiParseResult(TypedDict):
    parse: Parse

class Preference(TypedDict):
    key: str
    value: Any
    description: NotRequired[str]

class Emojis:
    toggle_on = "<:toggle_on:1401234525501001820>"
    toggle_off = "<:toggle_off:1401234593197068429>"