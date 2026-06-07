"""
OBS Diagnostic - Check group/scene contents recursively
"""
import obsws_python as obs
import sys

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

HOST = "127.0.0.1"
PORT = 4455
PASS = "xIC2SuivwblbJ3oN"

req = obs.ReqClient(host=HOST, port=PORT, password=PASS)
prog = req.get_current_program_scene()
prog_name = getattr(prog, 'current_program_scene_name', None)
print(f"Program scene: '{prog_name}'")

def dump_items(scene_or_group, indent=0):
    pad = "  " * indent
    try:
        resp = req.get_scene_item_list(scene_or_group)
        items = getattr(resp, 'scene_items', [])
    except Exception as e:
        print(f"{pad}[ERROR get_scene_item_list('{scene_or_group}'): {e}]")
        return

    for item in items:
        name     = item.get('sourceName', '?')
        enabled  = item.get('sceneItemEnabled', '?')
        is_group = item.get('isGroup', False)
        stype    = item.get('sourceType', '?')
        print(f"{pad}'{name}' | enabled={enabled} | isGroup={is_group} | type={stype}")

        # Recurse into scenes used as sources (sourceType=SCENE) and groups
        if is_group or stype == 'OBS_SOURCE_TYPE_SCENE':
            print(f"{pad}  [expanding nested scene/group '{name}']")
            dump_items(name, indent + 2)

dump_items(prog_name)

# Also check get_source_active for GOPRO
print("\n--- get_source_active('GOPRO') ---")
try:
    a = req.get_source_active('GOPRO')
    print(f"  videoActive  = {getattr(a,'video_active','?')}")
    print(f"  videoShowing = {getattr(a,'video_showing','?')}")
except Exception as e:
    print(f"  ERROR: {e}")

req.disconnect()
print("Done.")
