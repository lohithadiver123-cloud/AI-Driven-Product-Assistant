"""
Fallback in-memory/JSON database when MongoDB is unavailable.
Used for Milestone 1 demo purposes.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

# Data directory for JSON storage
DATA_DIR = os.path.join(os.path.dirname(__file__), ".demo_data")
os.makedirs(DATA_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.json")

# In-memory cache
_users_cache: Dict[str, Dict] = {}
_workspaces_cache: Dict[str, Dict] = {}
_feedback_cache: Dict[str, Dict] = {}

# Parsed-file cache, keyed by path. See _read_collection() for why this exists.
_PARSED: Dict[str, List[Dict]] = {}
_CACHE_MTIME: Dict[str, float] = {}


def _load_json(filepath: str) -> List[Dict]:
    """Load JSON file or return empty list."""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def _save_json(filepath: str, data: List[Dict]) -> None:
    """Save data to JSON file."""
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    # Our own write is the newest known state, so record it instead of forcing the next
    # read to re-parse what we just serialised.
    _PARSED[filepath] = data
    try:
        _CACHE_MTIME[filepath] = os.path.getmtime(filepath)
    except OSError:
        _CACHE_MTIME.pop(filepath, None)


def _read_collection(filepath: str) -> List[Dict]:
    """
    Return the parsed contents of a JSON collection, re-parsing only when it changed.

    Every fallback operation used to call json.load() on all three core files, so a single
    request re-parsed the whole feedback corpus from disk — at one point 54 MB, measured at
    ~0.5 s per call, on operations as small as a user lookup. Caching by modification time
    keeps the parse to once per process while still noticing a write made by any process.
    """
    try:
        mtime = os.path.getmtime(filepath)
    except OSError:
        return []
    if _CACHE_MTIME.get(filepath) == mtime:
        return _PARSED.get(filepath, [])
    data = _load_json(filepath)
    _PARSED[filepath] = data
    _CACHE_MTIME[filepath] = mtime
    return data


def _index_by(filepath: str, key: str) -> Dict[str, Dict]:
    """Load a JSON collection and index it by one of its fields."""
    return {
        str(row[key]): row
        for row in _read_collection(filepath)
        if isinstance(row, dict) and key in row
    }


def _load_cache() -> None:
    """Load all core data from JSON files into memory."""
    global _users_cache, _workspaces_cache, _feedback_cache

    _users_cache = _index_by(USERS_FILE, '_id')
    _workspaces_cache = _index_by(WORKSPACES_FILE, '_id')
    _feedback_cache = _index_by(FEEDBACK_FILE, '_id')


def _save_all() -> None:
    """Save all caches back to JSON files."""
    _save_json(USERS_FILE, list(_users_cache.values()))
    _save_json(WORKSPACES_FILE, list(_workspaces_cache.values()))
    _save_json(FEEDBACK_FILE, list(_feedback_cache.values()))


# ============= User Operations =============

async def create_user(user_data: Dict[str, Any]) -> Dict:
    """Create a new user."""
    _load_cache()
    user_id = str(len(_users_cache) + 1)
    user_data['_id'] = user_id
    user_data['created_at'] = datetime.utcnow().isoformat()
    user_data.setdefault('role', 'product_manager')
    user_data['workspace_ids'] = []
    _users_cache[user_id] = user_data
    _save_all()
    return user_data


async def find_user_by_email(email: str) -> Optional[Dict]:
    """Find user by email."""
    _load_cache()
    for user in _users_cache.values():
        if user.get('email') == email:
            return user
    return None


async def find_user_by_id(user_id: str) -> Optional[Dict]:
    """Find user by ID."""
    _load_cache()
    return _users_cache.get(user_id)


# ============= Workspace Operations =============

async def create_workspace(workspace_data: Dict[str, Any]) -> Dict:
    """Create a new workspace."""
    _load_cache()
    workspace_id = str(len(_workspaces_cache) + 1)
    workspace_data['_id'] = workspace_id
    workspace_data['created_at'] = datetime.utcnow().isoformat()
    _workspaces_cache[workspace_id] = workspace_data

    # Use the cache loaded above: find_user_by_id() would reload it and drop this workspace.
    if 'created_by' in workspace_data:
        user = _users_cache.get(str(workspace_data['created_by']))
        if user is not None:
            if 'workspace_ids' not in user:
                user['workspace_ids'] = []
            user['workspace_ids'].append(workspace_id)

    _save_all()
    return workspace_data


async def find_workspaces_by_user(user_id: str) -> List[Dict]:
    """Find all workspaces for a user."""
    _load_cache()
    return [w for w in _workspaces_cache.values() if w.get('created_by') == user_id]


async def find_workspace_by_id(workspace_id: str) -> Optional[Dict]:
    """Find a single workspace by its own id."""
    _load_cache()
    return _workspaces_cache.get(str(workspace_id))


# ============= Feedback Operations =============

async def create_feedback(feedback_data: Dict[str, Any]) -> Dict:
    """Create feedback entry."""
    _load_cache()
    feedback_id = str(len(_feedback_cache) + 1)
    feedback_data['_id'] = feedback_id
    feedback_data['created_at'] = datetime.now(timezone.utc).isoformat()
    _feedback_cache[feedback_id] = feedback_data
    _save_all()
    return feedback_data


async def create_feedback_batch(feedback_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create a batch of feedback entries in fallback db."""
    _load_cache()
    current_count = len(_feedback_cache)
    now_iso = datetime.now(timezone.utc).isoformat()
    created = []
    for i, item in enumerate(feedback_list):
        fid = str(current_count + i + 1)
        item['_id'] = fid
        item.setdefault('created_at', now_iso)
        _feedback_cache[fid] = item
        created.append(item)
    _save_all()
    return created


async def find_feedback_by_workspace(workspace_id: str, skip: int = 0, limit: int = 20) -> tuple[List[Dict], int]:
    """Find feedback for a workspace with pagination."""
    _load_cache()
    items = [f for f in _feedback_cache.values() if f.get('workspace_id') == workspace_id]
    total = len(items)
    return items[skip:skip+limit], total


async def update_feedback(feedback_id: str, updates: Dict) -> Optional[Dict]:
    """Update feedback entry."""
    _load_cache()
    if feedback_id in _feedback_cache:
        _feedback_cache[feedback_id].update(updates)
        _save_all()
        return _feedback_cache[feedback_id]
    return None


async def find_all_feedback_by_workspace(workspace_id: str) -> List[Dict]:
    """Find all feedback for a workspace without pagination."""
    _load_cache()
    return [f for f in _feedback_cache.values() if f.get('workspace_id') == workspace_id]


# ============= Insights Operations =============

INSIGHTS_FILE = os.path.join(DATA_DIR, "insights.json")
_insights_cache: Dict[str, Dict] = {}


def _load_insights_cache() -> None:
    global _insights_cache
    _insights_cache = _index_by(INSIGHTS_FILE, 'workspace_id')


async def save_workspace_insights(workspace_id: str, insights_data: Dict[str, Any]) -> Dict:
    """Save or update workspace insights in fallback DB."""
    _load_insights_cache()
    _insights_cache[workspace_id] = insights_data
    _save_json(INSIGHTS_FILE, list(_insights_cache.values()))
    return insights_data


async def get_workspace_insights(workspace_id: str) -> Optional[Dict]:
    """Get cached workspace insights in fallback DB."""
    _load_insights_cache()
    return _insights_cache.get(workspace_id)


# ============= Milestone 3: PRD Operations =============

PRDS_FILE = os.path.join(DATA_DIR, "prds.json")
_prds_cache: Dict[str, Dict] = {}

def _load_prds_cache() -> None:
    global _prds_cache
    _prds_cache = _index_by(PRDS_FILE, 'id')

async def save_prd(prd_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_prds_cache()
    _prds_cache[prd_data['id']] = prd_data
    _save_json(PRDS_FILE, list(_prds_cache.values()))
    return prd_data

async def find_prds_by_workspace(workspace_id: str) -> List[Dict]:
    _load_prds_cache()
    return [p for p in _prds_cache.values() if p.get('workspace_id') == workspace_id]

async def find_prd_by_id(prd_id: str) -> Optional[Dict]:
    _load_prds_cache()
    return _prds_cache.get(prd_id)

async def update_prd(prd_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
    _load_prds_cache()
    if prd_id in _prds_cache:
        _prds_cache[prd_id].update(updates)
        _save_json(PRDS_FILE, list(_prds_cache.values()))
        return _prds_cache[prd_id]
    return None

async def delete_prd(prd_id: str) -> bool:
    _load_prds_cache()
    if prd_id in _prds_cache:
        del _prds_cache[prd_id]
        _save_json(PRDS_FILE, list(_prds_cache.values()))
        return True
    return False


# ============= Milestone 3: User Story Operations =============

STORIES_FILE = os.path.join(DATA_DIR, "user_stories.json")
_stories_cache: Dict[str, Dict] = {}

def _load_stories_cache() -> None:
    global _stories_cache
    _stories_cache = _index_by(STORIES_FILE, 'id')

async def save_user_story(story_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_stories_cache()
    _stories_cache[story_data['id']] = story_data
    _save_json(STORIES_FILE, list(_stories_cache.values()))
    return story_data

async def bulk_save_stories(stories_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _load_stories_cache()
    for s in stories_list:
        _stories_cache[s['id']] = s
    _save_json(STORIES_FILE, list(_stories_cache.values()))
    return stories_list

async def find_stories_by_workspace(workspace_id: str, prd_id: Optional[str] = None) -> List[Dict]:
    _load_stories_cache()
    items = [s for s in _stories_cache.values() if s.get('workspace_id') == workspace_id]
    if prd_id:
        items = [s for s in items if s.get('prd_id') == prd_id]
    return items

async def find_story_by_id(story_id: str) -> Optional[Dict]:
    _load_stories_cache()
    return _stories_cache.get(story_id)

async def update_story(story_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
    _load_stories_cache()
    if story_id in _stories_cache:
        _stories_cache[story_id].update(updates)
        _save_json(STORIES_FILE, list(_stories_cache.values()))
        return _stories_cache[story_id]
    return None

async def delete_story(story_id: str) -> bool:
    _load_stories_cache()
    if story_id in _stories_cache:
        del _stories_cache[story_id]
        _save_json(STORIES_FILE, list(_stories_cache.values()))
        return True
    return False


# ============= Milestone 3: Prioritization Operations =============

PRIORITIZATION_FILE = os.path.join(DATA_DIR, "prioritization.json")
WEIGHTS_FILE = os.path.join(DATA_DIR, "framework_weights.json")
_prioritization_cache: Dict[str, Dict] = {}
_weights_cache: Dict[str, Dict] = {}

def _load_prioritization_cache() -> None:
    global _prioritization_cache
    _prioritization_cache = _index_by(PRIORITIZATION_FILE, 'id')

def _load_weights_cache() -> None:
    global _weights_cache
    _weights_cache = _index_by(WEIGHTS_FILE, 'workspace_id')

async def save_prioritization_item(item_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_prioritization_cache()
    _prioritization_cache[item_data['id']] = item_data
    _save_json(PRIORITIZATION_FILE, list(_prioritization_cache.values()))
    return item_data

async def bulk_save_prioritization_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    _load_prioritization_cache()
    for item in items:
        _prioritization_cache[item['id']] = item
    _save_json(PRIORITIZATION_FILE, list(_prioritization_cache.values()))
    return items

async def find_prioritization_items_by_workspace(workspace_id: str) -> List[Dict]:
    _load_prioritization_cache()
    return [i for i in _prioritization_cache.values() if i.get('workspace_id') == workspace_id]


async def find_prioritization_item_by_id(item_id: str) -> Optional[Dict]:
    """Find a single prioritization item by its own id (not workspace-scoped)."""
    _load_prioritization_cache()
    return _prioritization_cache.get(item_id)

async def update_prioritization_item(item_id: str, updates: Dict[str, Any]) -> Optional[Dict]:
    _load_prioritization_cache()
    if item_id in _prioritization_cache:
        _prioritization_cache[item_id].update(updates)
        _save_json(PRIORITIZATION_FILE, list(_prioritization_cache.values()))
        return _prioritization_cache[item_id]
    return None

async def delete_prioritization_item(item_id: str) -> bool:
    _load_prioritization_cache()
    if item_id in _prioritization_cache:
        del _prioritization_cache[item_id]
        _save_json(PRIORITIZATION_FILE, list(_prioritization_cache.values()))
        return True
    return False

async def get_workspace_weights(workspace_id: str) -> Optional[Dict]:
    _load_weights_cache()
    return _weights_cache.get(workspace_id)

async def save_workspace_weights(weights_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_weights_cache()
    _weights_cache[weights_data['workspace_id']] = weights_data
    _save_json(WEIGHTS_FILE, list(_weights_cache.values()))
    return weights_data


# ============= Milestone 3: Copilot Chat Operations =============

COPILOT_FILE = os.path.join(DATA_DIR, "copilot_chats.json")
_copilot_cache: List[Dict] = []

def _load_copilot_cache() -> None:
    global _copilot_cache
    _copilot_cache = _read_collection(COPILOT_FILE)

async def save_copilot_message(msg_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_copilot_cache()
    _copilot_cache.append(msg_data)
    _save_json(COPILOT_FILE, _copilot_cache)
    return msg_data

async def get_copilot_history(workspace_id: str, session_id: Optional[str] = None) -> List[Dict]:
    _load_copilot_cache()
    results = [m for m in _copilot_cache if m.get('workspace_id') == workspace_id]
    if session_id:
        results = [m for m in results if m.get('session_id') == session_id]
    return results

async def clear_copilot_history(workspace_id: str, session_id: Optional[str] = None) -> bool:
    global _copilot_cache
    _load_copilot_cache()
    if session_id:
        _copilot_cache = [m for m in _copilot_cache if not (m.get('workspace_id') == workspace_id and m.get('session_id') == session_id)]
    else:
        _copilot_cache = [m for m in _copilot_cache if m.get('workspace_id') != workspace_id]
    _save_json(COPILOT_FILE, _copilot_cache)
    return True

# ============= Milestone 4: Roadmap Operations =============

ROADMAPS_FILE = os.path.join(DATA_DIR, "roadmaps.json")
_roadmaps_cache: Dict[str, Dict] = {}

def _load_roadmaps_cache() -> None:
    global _roadmaps_cache
    _roadmaps_cache = _index_by(ROADMAPS_FILE, 'workspace_id')

async def save_roadmap(roadmap_data: Dict[str, Any]) -> Dict[str, Any]:
    """One roadmap per workspace — saving replaces the previous plan."""
    _load_roadmaps_cache()
    _roadmaps_cache[roadmap_data['workspace_id']] = roadmap_data
    _save_json(ROADMAPS_FILE, list(_roadmaps_cache.values()))
    return roadmap_data

async def get_roadmap(workspace_id: str) -> Optional[Dict]:
    _load_roadmaps_cache()
    return _roadmaps_cache.get(workspace_id)

async def delete_roadmap(workspace_id: str) -> bool:
    _load_roadmaps_cache()
    if workspace_id in _roadmaps_cache:
        del _roadmaps_cache[workspace_id]
        _save_json(ROADMAPS_FILE, list(_roadmaps_cache.values()))
        return True
    return False


# ============= Milestone 4: Report Operations =============

REPORTS_FILE = os.path.join(DATA_DIR, "reports.json")
_reports_cache: Dict[str, Dict] = {}

def _load_reports_cache() -> None:
    global _reports_cache
    _reports_cache = _index_by(REPORTS_FILE, 'id')

async def save_report(report_data: Dict[str, Any]) -> Dict[str, Any]:
    _load_reports_cache()
    _reports_cache[report_data['id']] = report_data
    _save_json(REPORTS_FILE, list(_reports_cache.values()))
    return report_data

async def find_reports_by_workspace(workspace_id: str) -> List[Dict]:
    _load_reports_cache()
    reports = [r for r in _reports_cache.values() if r.get('workspace_id') == workspace_id]
    return sorted(reports, key=lambda r: str(r.get('created_at') or ''), reverse=True)

async def find_report_by_id(report_id: str) -> Optional[Dict]:
    _load_reports_cache()
    return _reports_cache.get(report_id)

async def delete_report(report_id: str) -> bool:
    _load_reports_cache()
    if report_id in _reports_cache:
        del _reports_cache[report_id]
        _save_json(REPORTS_FILE, list(_reports_cache.values()))
        return True
    return False


print("Fallback JSON database loaded")


