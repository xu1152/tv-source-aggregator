"""Convert sources.json to TVBox-compatible formats."""
import json
import os

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(base_dir, 'sources.json'), 'r', encoding='utf-8') as f:
    data = json.load(f)

# Format 1: TXT (simplest, most compatible)
with open(os.path.join(base_dir, 'sources.txt'), 'w', encoding='utf-8') as f:
    for ch in data['lives']:
        name = ch['name']
        for url in ch['urls']:
            f.write(f"{name},{url}\n")

# Format 2: M3U
with open(os.path.join(base_dir, 'sources.m3u'), 'w', encoding='utf-8') as f:
    f.write('#EXTM3U\n')
    for ch in data['lives']:
        name = ch['name']
        group = ch.get('group', '')
        logo = ch.get('logo', '')
        for url in ch['urls']:
            f.write(f'#EXTINF:-1 group-title="{group}" tvg-logo="{logo}",{name}\n')
            f.write(f'{url}\n')

# Format 3: Flat JSON array (no wrapper)
flat = [{
    'name': ch['name'],
    'urls': ch['urls'],
    'group': ch.get('group', '')
} for ch in data['lives']]
with open(os.path.join(base_dir, 'sources_flat.json'), 'w', encoding='utf-8') as f:
    json.dump(flat, f, ensure_ascii=False, indent=2)

# Update multi-repo wrapper to point to TXT as primary
wrapper = {
    'urls': [
        {
            'url': f'https://raw.githubusercontent.com/xu1152/tv-source-aggregator/master/sources.txt',
            'name': '484\u4e2a\u76f4\u64ad\u9891\u9053'
        }
    ]
}
with open(os.path.join(base_dir, 'tvbox.json'), 'w', encoding='utf-8') as f:
    json.dump(wrapper, f, ensure_ascii=False, indent=2)

print('Done!')
print(f'TXT: {sum(1 for _ in open(os.path.join(base_dir, "sources.txt"), encoding="utf-8"))} lines')
print(f'M3U: {sum(1 for _ in open(os.path.join(base_dir, "sources.m3u"), encoding="utf-8"))} lines')
