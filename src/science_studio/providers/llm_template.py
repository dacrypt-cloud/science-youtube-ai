"""Deterministic fallback 'AI' — real extractive/templated generation, $0, offline.

This is NOT a fake LLM: it performs genuine text processing (sentence scoring,
keyword extraction, outline assembly) so the pipeline works with zero API keys.
Quality is lower than Gemini; the provider name is always recorded so outputs
are honest about how they were produced.

All selection is extractive + hygiene-filtered: web chrome (cookie banners,
paywalls, nav menus), citation artifacts, and off-topic sentences are dropped
before anything can reach claims or narration.
"""
from __future__ import annotations
import re
from collections import Counter
from .base import AIProvider, ProviderStatus


STOP = set("""a an the and or but if then else when while of at by for with about into
through during before after above below to from up down in out on off over under again
further once here there all any both each few more most other some such no nor not only
own same so than too very can will just don should now is are was were be been being
have has had having do does did doing would could ought i you he she it we they them
his her its our their this that these those as than""".split())

# Web-chrome / boilerplate markers: any sentence containing these is never
# spoken or claimed (generic site furniture, not science).
CHROME_MARKERS = (
    "thank you for visiting", "to ensure continued support", "displaying the site",
    "cookie", "subscribe", "sign in", "log in", "all rights reserved",
    "http://", "https://", "www.", ".com/", "©", "privacy policy",
    "terms of service", "terms and conditions", "newsletter",
    "|", "journals have moved", "nature link", "science direct",
    "download pdf", "full text", "read more", "click here", "page not found",
    "access article", "show more", "download citation", "cite this article",
)

# Sentence-leading citation/section artifacts ("18 implemented an explicit…",
# "Abstract Lightning discharges…").
LEAD_JUNK_RE = re.compile(r"^\s*(\d{1,3}\s+[a-z]|abstract\b|references\b|acknowledg)", re.I)

# Discourse-domain drift veto (generic): strong markers of a DIFFERENT discourse
# (aviation engineering, space missions, education research, ...) veto a sentence
# UNLESS the question itself belongs to that domain. Each domain lists
# (question_anchors, veto_markers). Matching is whole-word, case-insensitive.
DISCOURSE_DOMAINS: dict[str, tuple[set[str], set[str]]] = {
    "aviation": (
        {"aircraft", "airplane", "aeroplane", "flight", "aviation", "pilot",
         "airport", "airline", "airliner"},
        {"aircraft", "airplane", "aeroplane", "airport", "radome", "fuselage",
         "avionics", "airliner", "airlines", "airframe", "aviation",
         "airspace", "air traffic"},
    ),
    "ancient_history": (
        {"history", "ancient", "roman", "rome", "egypt", "greek", "greece",
         "war", "century", "medieval", "emperor", "empire", "archaeology",
         "historian", "pliny"},
        {"emperor", "dynasty", "pharaoh", "caesar", "viking", "crusade",
         "legion", "gladiator", "pliny", "domitian", "cicero", "seneca"},
    ),
    "space": (
        {"space", "planet", "planets", "star", "stars", "galaxy", "nasa",
         "astronom", "astronomy", "orbit", "satellite", "cosmos", "telescope",
         "mars", "venus", "jupiter", "saturn", "moon", "lunar", "solar system"},
        {"spacecraft", "exoplanet", "astronaut", "cosmonaut", "martian",
         "venusian", "jovian", "venus", "mars", "jupiter", "saturn",
         "light-year", "light year"},
    ),
    "education": (
        {"school", "student", "students", "education", "learn", "teach",
         "classroom", "curriculum", "teacher", "university", "college"},
        {"undergraduate", "postgraduate", "classroom", "curriculum",
         "pedagogy", "pedagogical", "coursework", "lesson plan"},
    ),
    "finance": (
        {"econom", "economy", "financ", "market", "money", "bank", "invest",
         "bitcoin", "stock", "trade"},
        {"bitcoin", "blockchain", "cryptocurrency", "stock market",
         "portfolio", "shareholder"},
    ),
    "legal": (
        {"law", "legal", "court", "lawsuit", "justice", "trial lawyer"},
        {"plaintiff", "defendant", "litigation", "lawsuit", "appellant",
         "court ruled"},
    ),
    "sports": (
        {"sport", "sports", "olympic", "football", "soccer", "athlete",
         "tournament", "championship"},
        {"olympic", "olympics", "fifa", "championship", "tournament",
         "medalist", "world cup"},
    ),
    "politics": (
        {"election", "politic", "president", "govern", "vote", "minister",
         "parliament", "senate"},
        {"election", "parliament", "senate", "referendum", "campaign trail",
         "exit poll"},
    ),
    "religion": (
        {"religion", "god", "church", "faith", "bible", "quran", "theolog"},
        {"sermon", "quran", "talmud", "catechism", "beatitude"},
    ),
    # Paper-discourse is never documentary narration. Applies to every topic
    # (empty question anchors = always active): papers say "in this paper",
    # documentaries never do.
    "paper": (
        set(),
        {"here we present", "here we show", "here we report",
         "here we demonstrate", "in this paper", "in this study",
         "this paper presents", "this study presents", "we present the",
         "we report the", "we demonstrate the", "a review of",
         "an overview of", "a survey of", "this work describes",
         "this contribution will", "the aim of this", "as follows",
         "et al", "ibid", "we present", "we propose", "we investigate",
         "we analyze", "we analyse", "we report", "we show", "we demonstrate",
         "we discuss", "as we discuss", "as discussed", "will discuss",
         "this paper", "this study", "this work", "our results",
         "our findings", "our data", "our model", "our analysis",
         "our method", "figure", "figures", "fig", "table shows",
         "tables show", "as shown in", "see section", "in section"},
    ),
}


def domain_veto(text: str, anchors: list[str] | None) -> str:
    """Return the vetoing domain name if `text` belongs to a discourse domain
    the question is not about; else "". Generic cross-domain drift filter."""
    if not anchors or not text:
        return ""
    aq = " ".join(anchors).lower()
    tl = text.lower()
    for domain, (q_anchors, markers) in DISCOURSE_DOMAINS.items():
        if any(q in aq for q in q_anchors):
            continue  # question belongs to this domain: no veto
        for m in markers:
            if re.search(r"\b" + re.escape(m) + r"\b", tl):
                return domain
    return ""

_STEM_SUFFIXES = ("ational", "tional", "izer", "ation", "ator", "alism",
                  "iveness", "fulness", "tion", "ence", "ance", "ment",
                  "ness", "able", "ible", "ing", "ied", "ies", "ed", "es", "s")


def stem(word: str) -> str:
    """Light suffix stemmer for topical matching (plurals, tenses)."""
    w = (word or "").lower()
    for suf in _STEM_SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            return w[:-len(suf)]
    return w


def sent_stems(sentence: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", (sentence or "").lower())} - STOP


# Generic science-English finite-verb lexicon (base + inflected forms). A sentence
# with no lexicon verb and no auxiliary is a title fragment, table row, or
# heading — never narration. Deliberately excludes -ing-only forms (gerunds
# dominate titles: "Nowcasting lightning occurrence...").
VERB_LEXICON = {
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "having", "do", "does", "did", "doing", "will", "would", "can", "could",
    "may", "might", "must", "shall", "should",
    "show", "shows", "showed", "shown", "reveal", "reveals", "revealed",
    "suggest", "suggests", "suggested", "indicate", "indicates", "indicated",
    "cause", "causes", "caused", "lead", "leads", "led",
    "produce", "produces", "produced", "mean", "means", "meant",
    "occur", "occurs", "occurred", "happen", "happens", "happened",
    "form", "forms", "formed", "create", "creates", "created",
    "make", "makes", "made", "contain", "contains", "contained",
    "include", "includes", "included", "involve", "involves", "involved",
    "require", "requires", "required", "depend", "depends", "depended",
    "increase", "increases", "increased", "decrease", "decreases", "decreased",
    "affect", "affects", "affected", "result", "results", "resulted",
    "follow", "follows", "followed", "begin", "begins", "began",
    "continue", "continues", "continued", "remain", "remains", "remained",
    "appear", "appears", "appeared", "seem", "seems", "seemed",
    "tend", "tends", "tended", "become", "becomes", "became",
    "use", "uses", "used", "follow", "take", "takes", "took",
    "give", "gives", "gave", "get", "gets", "got", "go", "goes", "went",
    "come", "comes", "came", "start", "starts", "started",
    "end", "ends", "ended", "stop", "stops", "stopped",
    "rise", "rises", "rose", "risen", "fall", "falls", "fell", "fallen",
    "grow", "grows", "grew", "grown", "heat", "heats", "heated",
    "cool", "cools", "cooled", "expand", "expands", "expanded",
    "contract", "contracts", "move", "moves", "moved",
    "flow", "flows", "flowed", "run", "runs", "ran",
    "travel", "travels", "travelled", "traveled", "pass", "passes", "passed",
    "enter", "enters", "entered", "leave", "leaves", "left",
    "reach", "reaches", "reached", "hit", "hits",
    "strike", "strikes", "struck", "split", "splits",
    "carve", "carves", "carved", "slam", "slams", "slammed",
    "trigger", "triggers", "triggered", "spark", "sparks", "sparked",
    "ignite", "ignites", "ignited", "burn", "burns", "burned", "burnt",
    "glow", "glows", "glowed", "shine", "shines", "shone",
    "emit", "emits", "emitted", "release", "releases", "released",
    "absorb", "absorbs", "absorbed", "reflect", "reflects", "reflected",
    "scatter", "scatters", "scattered", "ionize", "ionizes", "ionized",
    "charge", "charges", "charged", "discharge", "discharges", "discharged",
    "attract", "attracts", "attracted", "repel", "repels", "repelled",
    "collide", "collides", "collided", "separate", "separates", "separated",
    "divide", "divides", "divided", "break", "breaks", "broke", "broken",
    "build", "builds", "built", "accumulate", "accumulates", "accumulated",
    "gather", "gathers", "gathered", "sink", "sinks", "sank",
    "lift", "lifts", "lifted", "carry", "carries", "carried",
    "transport", "transports", "transported", "transfer", "transfers",
    "transferred", "exchange", "exchanges", "exchanged",
    "convert", "converts", "converted", "transform", "transforms",
    "transformed", "generate", "generates", "generated",
    "radiate", "radiates", "radiated", "melt", "melts", "melted",
    "freeze", "freezes", "froze", "frozen", "evaporate", "evaporates",
    "evaporated", "condense", "condenses", "condensed",
    "drop", "drops", "dropped", "last", "lasts", "lasted",
    "spread", "spreads", "spread", "cover", "covers", "covered",
    "fill", "fills", "filled", "surround", "surrounds", "surrounded",
    "hold", "holds", "held", "store", "stores", "stored",
    "trap", "traps", "trapped", "block", "blocks", "blocked",
    "allow", "allows", "allowed", "prevent", "prevents", "prevented",
    "protect", "protects", "protected", "damage", "damages", "damaged",
    "destroy", "destroys", "destroyed", "kill", "kills", "killed",
    "injure", "injures", "injured", "threaten", "threatens", "threatened",
    "warn", "warns", "warned", "predict", "predicts", "predicted",
    "forecast", "forecasts", "forecasted", "detect", "detects", "detected",
    "observe", "observes", "observed", "measure", "measures", "measured",
    "record", "records", "recorded", "monitor", "monitors", "monitored",
    "track", "tracks", "tracked", "map", "maps", "mapped",
    "capture", "captures", "captured", "find", "finds", "found",
    "discover", "discovers", "discovered", "prove", "proves", "proved",
    "proven", "confirm", "confirms", "confirmed", "support", "supports",
    "supported", "challenge", "challenges", "challenged",
    "explain", "explains", "explained", "describe", "describes", "described",
    "define", "defines", "defined", "represent", "represents", "represented",
    "clarify", "clarifies", "clarified", "imply", "implies", "implied",
    "infer", "infers", "inferred", "conclude", "concludes", "concluded",
    "argue", "argues", "argued", "claim", "claims", "claimed",
    "state", "states", "stated", "report", "reports", "reported",
    "note", "notes", "noted", "add", "adds", "added",
    "agree", "agrees", "agreed", "disagree", "disagrees", "disagreed",
    "debate", "debates", "debated", "discuss", "discusses", "discussed",
    "propose", "proposes", "proposed", "predict", "assume", "assumes",
    "assumed", "estimate", "estimates", "estimated", "calculate",
    "calculates", "calculated", "compute", "computes", "computed",
    "derive", "derives", "derived", "solve", "solves", "solved",
    "test", "tests", "tested", "verify", "verifies", "verified",
    "validate", "validates", "validated", "check", "checks", "checked",
    "compare", "compares", "compared", "match", "matches", "matched",
    "fit", "fits", "fitted", "vary", "varies", "varied",
    "differ", "differs", "differed", "range", "ranges", "ranged",
    "span", "spans", "spanned", "extend", "extends", "extended",
    "cross", "crosses", "crossed", "propagate", "propagates", "propagated",
    "penetrate", "penetrates", "penetrated", "diffuse", "diffuses",
    "diffused", "oscillate", "oscillates", "vibrate", "vibrates",
    "rotate", "rotates", "rotated", "spin", "spins", "orbit", "orbits",
    "orbited", "accelerate", "accelerates", "accelerated",
    "drift", "drifts", "drifted", "migrate", "migrates", "migrated",
    "evolve", "evolves", "evolved", "develop", "develops", "developed",
    "decay", "decays", "decayed", "fade", "fades", "faded",
    "dissipate", "dissipates", "dissipated", "vanish", "vanishes",
    "vanished", "disappear", "disappears", "disappeared",
    "emerge", "emerges", "emerged", "arise", "arises", "arose",
    "exist", "exists", "existed", "persist", "persists", "persisted",
    "survive", "survives", "survived", "thrive", "thrives",
    "live", "lives", "lived", "die", "dies", "died",
    "feed", "feeds", "fed", "consume", "consumes", "consumed",
    "erupt", "erupts", "erupted", "explode", "explodes", "exploded",
    "burst", "bursts", "burst", "rupture", "ruptures", "ruptured",
    "crack", "cracks", "cracked", "shatter", "shatters", "shattered",
    "collapse", "collapses", "collapsed", "crash", "crashes", "crashed",
    "flash", "flashes", "flashed", "flicker", "flickers", "flickered",
    "blaze", "blazes", "blazed", "threaten", "loft", "lofts", "lofted",
    "soar", "soars", "plunge", "plunges", "plunged", "surge", "surges",
    "surged", "pulse", "pulses", "pulsed",
    "analyze", "analyzes", "analyzed", "analyse", "analyses", "analysed",
    "investigate", "investigates", "investigated", "relate", "relates",
    "related", "originate", "originates", "originated", "recommend",
    "recommends", "recommended", "change", "changes", "changed",
    "publish", "publishes", "published", "fuel", "fuels", "fueled",
    "drive", "drives", "driven", "drove", "shape", "shapes", "shaped",
    "control", "controls", "controlled", "link", "links", "linked",
    "connect", "connects", "connected", "couple", "couples", "coupled",
    "improve", "improves", "improved", "benefit", "benefits", "benefited",
    "account", "accounts", "accounted",
}
# Lexicon verbs that are equally common as nouns in science prose ("impulse
# charge moment change", "forecast horizon", "breakdown pulses", "excited
# states", "control group", "model runs"). They only count as verb evidence
# with syntactic company (auxiliary, determiner, or comma).
AMBIG_VERBS = {
    "charge", "charges", "charged", "discharge", "discharges", "discharged",
    "pulse", "pulses", "pulsed", "strike", "strikes", "struck",
    "flash", "flashes", "flashed", "forecast", "forecasts", "forecasted",
    "report", "reports", "reported", "state", "states", "stated",
    "note", "notes", "noted", "claim", "claims", "claimed",
    "result", "results", "resulted", "range", "ranges", "ranged",
    "cover", "covers", "covered", "last", "lasts", "lasted",
    "fit", "fits", "fitted", "map", "maps", "mapped",
    "match", "matches", "matched", "flow", "flows", "flowed",
    "pass", "passes", "passed", "cross", "crosses", "crossed",
    "burn", "burns", "burned", "burnt", "spark", "sparks", "sparked",
    "transfer", "transfers", "transferred", "form", "forms", "formed",
    "use", "uses", "used", "test", "tests", "tested",
    "check", "checks", "checked", "control", "controls", "controlled",
    "link", "links", "linked", "shape", "shapes", "shaped",
    "contract", "contracts", "run", "runs", "ran", "hit", "hits",
    "lead", "mean", "means", "meant", "trap", "traps", "trapped",
    "block", "blocks", "blocked", "challenge", "challenges", "challenged",
    "monitor", "monitors", "monitored", "measure", "measures", "measured",
    "track", "tracks", "tracked", "estimate", "estimates", "estimated",
    "debate", "debates", "debated", "glow", "glows", "glowed",
    "release", "releases", "released", "exchange", "exchanges", "exchanged",
    "drop", "drops", "dropped", "sink", "sinks", "sank",
    "record", "records", "recorded", "crash", "crashes", "crashed",
    "collapse", "collapses", "collapsed", "burst", "bursts",
    "rupture", "ruptures", "ruptured", "crack", "cracks", "cracked",
    "surge", "surges", "surged", "spin", "spins", "orbit", "orbits",
    "orbited", "drift", "drifts", "drifted", "decay", "decays", "decayed",
    "feed", "feeds", "fed", "fuel", "fuels", "fueled",
    "change", "changes", "changed", "span", "spans", "spanned",
    "couple",
}
_VERB_RE = re.compile(r"\b(" + "|".join(sorted(VERB_LEXICON, key=len, reverse=True)) + r")\b", re.I)
_AUX_RE = re.compile(
    r"\b(is|are|was|were|be|been|being|have|has|had|having|do|does|did|doing|"
    r"will|would|can|could|may|might|must|shall|should)\b", re.I)
HYPHENS = "-\u2010\u2011\u2012\u2013\u2014"
_ART_RE = re.compile(
    r"\b(the|a|an|this|that|these|those|its|their|his|her|our|your|"
    r"such|each|every|both|all|no)\b", re.I)
# Section headers glued to prose without punctuation ("...dataset Introduction
# Lightning is...") mark a structural splice: split before them.
_HEADER_RE = re.compile(
    r"(?<=[a-z])\s+(?=(?:Introduction|Abstract|Conclusions?|References?|"
    r"Methods?|Results?|Discussions?|Background|Summary|Keywords?|"
    r"Acknowledg(e)?ments?)\b)")
_HEADER_LEAD_RE = re.compile(
    r"^(?:Introduction|Abstract|Conclusions?|References?|Methods?|Results?|"
    r"Discussions?|Background|Summary|Keywords?|Acknowledg(e)?ments?)\s+(?=[A-Z])")


def _headless_start(s: str) -> bool:
    """Leading lowercase verb ("implemented an explicit...", "benefit from..."):
    the subject was a stripped citation/list marker — a headless fragment,
    never narration. Lowercase non-verbs ("pH", "eV") still pass."""
    m = re.match(r"^([a-z][a-z\-]*)", s)
    if not m:
        return False
    w = m.group(1)
    return bool(re.search(r"(?:ed|ing|s)$", w)) or w in VERB_LEXICON


# Abbreviations that must not split sentences ("etc. benefit" stays whole).
ABBREVIATIONS = ("etc.", "e.g.", "i.e.", "vs.", "al.", "Fig.", "fig.",
                 "Mr.", "Mrs.", "Dr.", "St.")


def split_sentences_raw(text: str) -> list[str]:
    """Split prose into ALL of its sentences without breaking abbreviations.

    Unlike split_sentences() (a research-text cleaner that drops headless
    fragments), this keeps every sentence: QA and diagram labels must judge
    the actual words, not a pre-filtered subset.
    """
    tmp = text or ""
    for abbr in ABBREVIATIONS:
        tmp = tmp.replace(abbr, abbr.replace(".", "․"))
    return [s.strip().replace("․", ".")
            for s in re.split(r"(?<=[.!?])\s+", tmp) if s.strip()]


def is_clean_sentence(s: str, anchors: list[str] | None = None) -> bool:
    """Hygiene gate: True if the sentence may be spoken or claimed."""
    if not s or not (30 <= len(s) <= 450):
        return False
    sl = s.lower()
    for m in CHROME_MARKERS:
        if m in sl:
            return False
    if LEAD_JUNK_RE.search(s):
        return False
    # digit-heavy lines are tables/citations, not narration
    digits = sum(c.isdigit() for c in s)
    if digits > len(s) * 0.15:
        return False
    if anchors:
        astems = {stem(a) for a in anchors}
        if not (sent_stems(s) & astems):
            return False
        if domain_veto(s, anchors):
            return False
        # ALL-CAPS lines are titles/headers, never narration.
        letters = [c for c in s if c.isalpha()]
        if len(letters) > 20 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
            return False
        # Unbalanced parentheses = cut-off fragment, never a full sentence.
        if s.count("(") != s.count(")"):
            return False
        if _headless_start(s):
            return False
        # Title-Case fragments are paper titles, not sentences.
        words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", s)]
        if len(words) >= 4:
            caps = sum(1 for w in words[1:] if w[0].isupper())
            if caps / max(1, len(words) - 1) > 0.5:
                return False
        # No finite verb (auxiliary or lexicon) = title fragment, table row,
        # or heading — never narration. Lexicon, not endings: plural nouns
        # ("parameters", "techniques") must not pass as verbs. A verb with no
        # words after it ("...lightning discharges.") is a plural noun or an
        # ellipsis, not a finite verb, and does not count.
        # Finite-verb evidence, discounting trailing plural nouns ("...lightning
        # discharges."). A lone ambiguous hit needs syntactic company (a
        # determiner or a comma) — bare noun chains are paper titles
        # ("Physical mechanism of initial breakdown pulses and narrow bipolar
        # events in lightning discharges.").
        hits = []
        for m in _VERB_RE.finditer(s):
            if not re.search(r"[A-Za-z]", s[m.end():]):
                continue  # trailing plural noun ("...lightning discharges.")
            if m.start() > 0 and s[m.start() - 1] in HYPHENS:
                continue  # hyphen fragment ("cross-correlation")
            if m.end() < len(s) and s[m.end()] in HYPHENS:
                continue
            if not re.search(r"[A-Za-z]", s[:m.start()]):
                continue  # first word: title or imperative, not a finite verb
            hits.append(m.group(0).lower())
        if not hits:
            return False
        if all(h in AMBIG_VERBS for h in hits):
            # Only noun-prone verbs ("charge", "change", "forecast"): they
            # count only with syntactic company — auxiliaries, determiners,
            # or commas ("forecast horizon" vs "the forecast predicts rain").
            if "," not in s and not _AUX_RE.search(s) and not _ART_RE.search(s):
                return False
        # Long, comma-less, auxiliary-less strings are spliced title salads,
        # not sentences ("...forecast horizon A physics-guided..."). Real
        # 140+ char sentences always carry an auxiliary or a comma.
        if len(s) > 140 and "," not in s and not _AUX_RE.search(s):
            return False
    return True


def keywords(text: str, n: int = 12) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    c = Counter(w for w in words if w not in STOP)
    return [w for w, _ in c.most_common(n)]


def _preclean(text: str) -> str:
    # blank line = structural boundary (title/body, heading/paragraph): split.
    text = re.sub(r"\n\s*\n+", ". ", text)
    # engine-side title references, never spoken: (see: Some Title Here)
    text = re.sub(r"\(see:[^)\n]{0,300}\)", " ", text)
    # remove source attribution tails like: [S018] (Publisher, 2026).
    text = re.sub(r"\[[A-Z]\d{2,4}\]", " ", text)
    text = re.sub(r"\(\s*[^,()\n]{0,60},\s*(\?|\d{4})\s*\)\.?", " ", text)
    text = re.sub(r"\bABSTRACT\b:? ?", " ", text)
    # AFTER attribution strips (they create it): "TGFs, ." -> "TGFs."
    text = re.sub(r",\s*\.", ".", text)
    return text


def split_sentences(text: str, anchors: list[str] | None = None) -> list[str]:
    text = _preclean(text)
    # section header glued to prose = structural splice: split before it.
    text = _HEADER_RE.sub(". ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    out = []
    for p in parts:
        p = p.strip()
        # salvage sentences with leading citation debris ("5 , 6 Lightning…")
        p = re.sub(r"^[\d\s,\-:;\(\)\[\]\.]+", "", p).strip()
        # strip a leading section header when prose follows ("Introduction
        # Lightning is..." -> "Lightning is..."); keep it when lowercase
        # follows ("Background levels rise..." is a real sentence).
        p = _HEADER_LEAD_RE.sub("", p).strip()
        if _headless_start(p):
            continue
        # drop truncated fragments (no terminal punctuation, cut mid-word)
        if len(p) > 40 and p[-1:] in ".!?":
            if is_clean_sentence(p, anchors):
                out.append(p)
    return out


def score_sentences(sentences: list[str], keys: list[str]) -> list[tuple[float, str]]:
    kset = set(keys)
    out = []
    for s in sentences:
        toks = set(re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", s.lower()))
        overlap = len(toks & kset)
        # prefer medium-length informative sentences
        length_pen = 1.0 if 60 < len(s) < 300 else 0.6
        out.append((overlap * length_pen, s))
    out.sort(reverse=True, key=lambda x: x[0])
    return out


class TemplateAIProvider(AIProvider):
    name = "template-fallback"

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.name, True, True, "always available, offline, deterministic")

    # The research/story modules call targeted helpers below rather than free-form
    # generation, which keeps output structured.
    def generate(self, prompt: str, *, system: str = "", max_tokens: int = 2000,
                 temperature: float = 0.4) -> str:
        # Generic handler: extractive summary of whatever context is embedded.
        sents = split_sentences(prompt)
        if not sents:
            return "No content available to summarize."
        keys = keywords(prompt)
        ranked = score_sentences(sents, keys)
        budget = max(300, min(max_tokens * 4, 6000))
        out, total = [], 0
        for _, s in ranked:
            if total + len(s) > budget:
                break
            out.append(s)
            total += len(s)
        return " ".join(out) if out else sents[0]

    # ── structured helpers used by pipeline stages ──
    def expand_questions(self, idea: str, central: str) -> list[str]:
        base = central or idea
        return [
            f"What is the core mechanism behind {base}?",
            f"What causes {base}, step by step?",
            f"What background concepts are needed to understand {base}?",
            f"What evidence supports the current understanding of {base}?",
            f"What are common misconceptions about {base}?",
            f"What remains uncertain or debated about {base}?",
            f"What is the history of discovery for {base}?",
            f"Why does {base} matter, and what are its consequences?",
        ]

    def extract_claims(self, text: str, source_id: str, max_claims: int = 10,
                       anchors: list[str] | None = None) -> list[dict]:
        sents = split_sentences(text, anchors=anchors)
        if not sents and anchors:
            sents = split_sentences(text)  # thin source: keep clean-but-ungated
        keys = keywords(text)
        ranked = score_sentences(sents, keys)[:max_claims]
        claims = []
        for i, (_, s) in enumerate(ranked):
            claims.append({
                "claim": s,
                "evidence_summary": s[:220],
                "confidence": "limited_evidence",
                "source_ids": [source_id],
            })
        return claims

    def assemble_script(self, scenes_outline: list[dict], evidence: str, target_words: int,
                        claims: list[dict] | None = None,
                        anchors: list[str] | None = None) -> list[dict]:
        """Build narration per scene from evidence sentences most relevant to
        each scene's title/claims (extractive, grounded, non-repeating).

        When `claims` is given, the scene's claim_ids are resolved to actual
        claim text for relevance ranking. When `anchors` is given, only
        sentences sharing topic stems are eligible (with clean fallback).
        """
        import re as _re
        sents = split_sentences(evidence, anchors=anchors)
        if len(sents) < len(scenes_outline) * 2:
            # thin/topical-mismatch evidence: keep chrome-clean sentences
            sents = split_sentences(evidence)
        # dedupe: evidence routinely contains snippet+fetched duplicates
        sents = list(dict.fromkeys(sents))
        if not sents:
            sents = ["Research is still being gathered for this topic."]
        claim_text = {c.get("claim_id", ""): c.get("claim", "") for c in (claims or [])}
        # Verified-vocabulary gate: narration must speak the claims' language
        # (>=2 shared stems), restricted to CONSENSUS stems (evidence-wide
        # document frequency >= 3) so drift-claim vocabulary can't smuggle
        # off-topic sentences into the narration.
        claim_vocab: set[str] = set()
        for c in (claims or []):
            claim_vocab |= sent_stems(c.get("claim", ""))
        df: dict[str, int] = {}
        for s in sents:
            for st in sent_stems(s):
                df[st] = df.get(st, 0) + 1
        consensus = {st for st, n in df.items() if n >= 3}
        narr_vocab = claim_vocab & consensus if consensus else claim_vocab
        per_scene = max(60, target_words // max(1, len(scenes_outline)))
        word_cap = int(per_scene * 1.05)
        sents_per_scene = max(3, per_scene // 18)
        used: set[str] = set()
        keys = keywords(evidence)
        kset = set(keys)

        def _eligible(s: str, need: int) -> bool:
            return (not narr_vocab) or len(sent_stems(s) & narr_vocab) >= need

        out = []
        n = len(scenes_outline)
        for idx, sc in enumerate(scenes_outline):
            claim_words = " ".join(claim_text.get(cid, "") for cid in sc.get("claim_ids", []))
            title_keys = set(_re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}",
                                         (sc.get("title", "") + " " + claim_words).lower())) - STOP
            pool = [s for s in sents if s not in used and _eligible(s, 2)]
            if len(pool) < sents_per_scene:
                pool = [s for s in sents if s not in used and _eligible(s, 1)]
            if len(pool) < sents_per_scene:
                pool = [s for s in sents if s not in used]
            # near-dupe suppression: a sentence must add >=3 new stems
            used_stems: set[str] = set()
            for u in used:
                used_stems |= sent_stems(u)
            fresh = [s for s in pool if len(sent_stems(s) - used_stems) >= 3]
            if len(fresh) >= sents_per_scene:
                pool = fresh
            if idx <= 1:
                # opening readability, with starvation fallback: prefer plain,
                # grammatical, medium-length sentences — but never silence.
                def _ro(s0: str) -> bool:
                    sl0 = s0.lower()
                    ac = len(_re.findall(r"\b[A-Z0-9]{2,}s?\b", s0))
                    hv = bool(_re.search(
                        r"\b(is|are|was|were|be|been|being|have|has|had|do|does|did|"
                        r"will|would|can|could|may|might|must|shall|should)\b", sl0))
                    return bool(hv and 80 <= len(s0) <= 260 and ac + s0.count("(") < 2)
                _rg = [s for s in pool if _ro(s)]
                pool = _rg if len(_rg) >= sents_per_scene else pool
            scored = []
            for s in pool:
                toks = set(_re.findall(r"[a-zA-Z][a-zA-Z\-]{3,}", s.lower()))
                title_hit = len(toks & title_keys)
                key_hit = len(toks & kset)
                bonus = 0.0
                sl = s.lower()
                # documentary shaping (selection only — never invented text):
                # open with curiosity, close with open questions.
                if idx == 0 and ("?" in s or any(w in sl for w in
                        ("mystery", "strange", "surprising", "puzzle", "imagine", "consider"))):
                    bonus = 2.0
                if idx == 0:
                    # hook readability: prefer short sentences, penalize jargon
                    # density (fraction of very long words).
                    words0 = s.split()
                    long_frac = sum(1 for w in words0 if len(w) >= 11) / max(1, len(words0))
                    if len(s) < 180:
                        bonus += 1.0
                    if long_frac > 0.25:
                        bonus -= 3.0
                if idx == n - 1 and any(w in sl for w in
                        ("unknown", "remains", "future", "researchers", "debate", "mystery")):
                    bonus = 2.0
                scored.append((title_hit * 3 + key_hit + bonus, s))
            scored.sort(reverse=True, key=lambda x: x[0])
            chunk = []
            for _, s in scored[:sents_per_scene]:
                chunk.append(s)
                used.add(s)
            if len(chunk) < 2:  # recycle least-used if evidence is thin
                for s in sents:
                    if s not in chunk:
                        chunk.append(s)
                    if len(chunk) >= sents_per_scene:
                        break
            # Titles are on-screen text; the voice speaks evidence sentences only.
            narration = " ".join(chunk)
            words = narration.split()
            if len(words) > word_cap:
                narration = " ".join(words[:word_cap])
                if "." in narration:
                    narration = narration.rsplit(".", 1)[0] + "."
            out.append({**sc, "narration": narration})
        return out
