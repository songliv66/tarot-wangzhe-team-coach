#!/usr/bin/env python3
"""Run the fixed synthetic demo offline and write a new, standalone report folder."""
import argparse
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples' / 'question-chain'
CHAPTERS = (
    ('01-start-team.md', '建队诊断', '先补协作证据'),
    ('02-research.md', '赛事研究', '统计与解释分开'),
    ('03-bp.md', '阵容 BP', '替代联动后续局'),
    ('04-training.md', '一次训练', '在时长内可执行'),
    ('05-review.md', '复盘迭代', '把判断变成观察'),
)


def tool(*args):
    process = subprocess.run([sys.executable, str(ROOT / 'scripts' / 'coachkit.py'), *args],
                             capture_output=True, text=True, timeout=15)
    if process.returncode:
        raise ValueError(process.stderr.strip() or 'offline tool failed')
    return json.loads(process.stdout)


def inline(value):
    value = html.escape(value, quote=True)
    value = re.sub(r'`([^`]+)`', r'<code>\1</code>', value)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)

    def link(match):
        target = html.unescape(match.group(2))
        if not (target.startswith('https://') or re.fullmatch(r'[A-Za-z0-9_.-]+', target)):
            return match.group(1)
        return '<a href="' + html.escape(target, quote=True) + '">' + match.group(1) + '</a>'

    return re.sub(r'\[([^\]]+)\]\(([^\s)]+)\)', link, value)


def markdown(source):
    """Render the small documented subset used by the fixed example, escaping input."""
    lines = source.splitlines()
    result, paragraph, code = [], [], []
    in_code, in_table, in_list = False, False, False

    def flush():
        if paragraph:
            result.append('<p>' + ' '.join(inline(p) for p in paragraph) + '</p>')
            paragraph.clear()

    for line in lines + ['']:
        if line.startswith('```'):
            flush()
            if in_code:
                result.append('<pre><code>' + html.escape('\n'.join(code)) + '</code></pre>')
                code.clear()
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if in_table and not line.startswith('|'):
            result.append('</tbody></table></div>')
            in_table = False
        if in_list and not re.match(r'^\s*(?:[-*]|\d+\.)\s+', line):
            result.append('</ul>')
            in_list = False
        if not line.strip():
            flush()
            continue
        heading = re.match(r'^(#{1,6})\s+(.+)', line)
        if heading:
            flush()
            level = min(6, len(heading.group(1)) + 1)
            result.append(f'<h{level}>' + inline(heading.group(2)) + f'</h{level}>')
        elif line.startswith('|'):
            flush()
            if re.fullmatch(r'[| :\-]+', line):
                continue
            cells = [inline(c.strip()) for c in line.strip().strip('|').split('|')]
            if not in_table:
                result.append('<div class="table-scroll"><table><thead><tr>' +
                              ''.join('<th>' + c + '</th>' for c in cells) + '</tr></thead><tbody>')
                in_table = True
            else:
                result.append('<tr>' + ''.join('<td>' + c + '</td>' for c in cells) + '</tr>')
        elif line.startswith('>'):
            flush()
            result.append('<blockquote>' + inline(line.lstrip('> ')) + '</blockquote>')
        elif re.match(r'^\s*(?:[-*]|\d+\.)\s+', line):
            flush()
            if not in_list:
                result.append('<ul>')
                in_list = True
            result.append('<li>' + inline(re.sub(r'^\s*(?:[-*]|\d+\.)\s+', '', line)) + '</li>')
        else:
            paragraph.append(line)
    if in_code:
        raise ValueError('unclosed example code fence')
    if in_table:
        result.append('</tbody></table></div>')
    if in_list:
        result.append('</ul>')
    return '\n'.join(result)


STYLE = '''
:root{color-scheme:light;--ink:#163239;--muted:#576c71;--paper:#f4f5ed;--line:#d8dfd4;--green:#246957;--gold:#c17b32}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.75 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
a{color:var(--green);text-underline-offset:3px}header,main,footer{max-width:1140px;margin:auto;padding:30px 32px}header{padding-top:55px;padding-bottom:24px}
.eyebrow{font-size:12px;letter-spacing:.16em;font-weight:750;color:var(--green)}h1{font-size:clamp(30px,5vw,55px);line-height:1.18;letter-spacing:-.04em;margin:15px 0 18px}
.lead{max-width:780px;color:var(--muted);font-size:18px}.pill{display:inline-block;border:1px solid var(--line);background:#fff9;padding:3px 11px;border-radius:20px;font-size:12px;margin-right:7px}
.notice{border-left:4px solid var(--gold);background:#fff7e8;padding:15px 20px;border-radius:0 10px 10px 0;font-size:14px}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:25px 0}.metric{padding:18px 20px;border:1px solid var(--line);border-radius:13px;background:#fff9}.metric b{display:block;font-size:27px;line-height:1.2}.metric span{font-size:12px;color:var(--muted)}
.tabs{position:sticky;top:0;background:var(--paper);padding:12px 0;display:flex;gap:8px;z-index:2;border-bottom:1px solid var(--line);overflow-x:auto}
.tabs button{font:inherit;white-space:nowrap;padding:9px 18px;border:1px solid var(--line);border-radius:9px;background:#fff;color:var(--ink);cursor:pointer}.tabs button[aria-selected=true]{background:var(--green);border-color:var(--green);color:#fff}.tabs button:focus-visible,a:focus-visible{outline:3px solid var(--gold);outline-offset:3px}
.chapter{margin-top:20px;padding:30px 34px;background:#fff;border:1px solid var(--line);border-radius:15px}.chapter[hidden]{display:none}.chapter h2{font-size:27px;margin:0 0 18px}.chapter h3{margin-top:32px;font-size:20px}.chapter h4{font-size:17px}.chapter p,.chapter li{max-width:920px}blockquote{margin:18px 0;padding:12px 18px;background:#edf5ef;border-left:3px solid var(--green)}
pre{padding:18px;background:#142c32;color:#e8f2e8;border-radius:9px;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.88em}p code,li code{background:#edf1e9;padding:2px 5px;border-radius:4px}
.table-scroll{overflow:auto;margin:18px 0}table{border-collapse:collapse;font-size:14px;width:100%;min-width:560px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid var(--line);padding:11px 12px}th{background:#eef3e9;font-size:12px}.results{margin-top:24px;border:1px solid var(--line);padding:22px;border-radius:13px}.results h2{margin-top:0;font-size:20px}.downloads{display:flex;gap:15px;flex-wrap:wrap;font-size:14px}.foot{font-size:13px;color:var(--muted);border-top:1px solid var(--line)}
@media(max-width:680px){header,main,footer{padding:22px 16px}header{padding-top:35px}.metrics{grid-template-columns:repeat(2,1fr)}.chapter{padding:22px 18px}.tabs button{padding:8px 12px}.lead{font-size:16px}}
'''


def page(chapters, analysis, bp, training):
    tabs, panels = [], []
    for i, ((filename, title, subtitle), text) in enumerate(zip(CHAPTERS, chapters)):
        tabs.append(f'<button id="tab-{i}" role="tab" aria-controls="panel-{i}" aria-selected="{str(i == 0).lower()}" tabindex="{0 if i == 0 else -1}">{i+1} · {title}</button>')
        panels.append(f'<section class="chapter" id="panel-{i}" role="tabpanel" aria-labelledby="tab-{i}"{ " hidden" if i else ""}><div class="eyebrow">STEP {i+1:02d} / {subtitle}</div>{markdown(text)}</section>')
    counts = ((str(len(CHAPTERS)), '个连贯阶段'),
              (str(analysis['games_in_dataset']), '局合成研究记录'),
              (str(len(bp['plans'])), '套已检查条件方案'),
              (str(training['total_minutes']), '分钟训练预算'))
    metrics = ''.join(f'<div class="metric"><b>{v}</b><span>{label}</span></div>' for v, label in counts)
    script = '''
const tabs=[...document.querySelectorAll('[role="tab"]')];
function activate(i){tabs.forEach((t,n)=>{const yes=n===i;t.setAttribute('aria-selected',String(yes));t.tabIndex=yes?0:-1;document.getElementById(t.getAttribute('aria-controls')).hidden=!yes;});}
tabs.forEach((tab,i)=>{tab.addEventListener('click',()=>activate(i));tab.addEventListener('keydown',e=>{let n=i;if(e.key==='ArrowRight')n=(i+1)%tabs.length;else if(e.key==='ArrowLeft')n=(i+tabs.length-1)%tabs.length;else if(e.key==='Home')n=0;else if(e.key==='End')n=tabs.length-1;else return;e.preventDefault();activate(n);tabs[n].focus();});});
'''
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="塔罗王者赛训：建队、研究、BP、训练与复盘的可复现合成演示。"><title>塔罗王者赛训 · 五阶段 Demo</title><style>{STYLE}</style></head>
<body><header><div class="eyebrow">TEAM COACH / OPEN SOURCE SKILL</div><h1>让每次训练，<br>都有下一步。</h1><p class="lead">从建队诊断到复盘迭代，沿着纸鸢队的五个问题，查看 AI 赛训工作流怎样把资料转成可验证的行动。</p><p><span class="pill">v2.1.0</span><span class="pill">离线可复现</span><span class="pill">Python 标准库</span></p><div class="notice"><strong>完整虚构案例。</strong>队伍、英雄池、比赛和事件均为合成材料；对话为预写模拟，工具实际执行统计与约束检查。页面没有模型调用，也不代表真实 KPL 研究或训练收益。</div><div class="metrics">{metrics}</div></header>
<main><nav class="tabs" role="tablist" aria-label="五阶段问题链">{''.join(tabs)}</nav>{''.join(panels)}
<section class="results"><h2>本次工具实际输出</h2><p>查看样本口径、条件方案校验和时长分配；约束通过不等于正式比赛合法。</p><div class="downloads"><a href="analysis.json">同队组合统计</a><a href="bp-check.json">BP 条件检查</a><a href="training-90.json">90 分钟分配</a><a href="training-60.json">60 分钟分配</a><a href="demo-report.md">完整 Markdown</a><a href="manifest.json">文件校验清单</a></div></section></main>
<footer class="foot">维护与联系：<strong>puddingvoid</strong> · <a href="https://github.com/songliv66/tarot-wangzhe-team-coach">GitHub 源码与使用说明</a> · 文档、工具与合成示例：MIT。外部资料权利另行适用。</footer><script>{script}</script></body></html>'''


def build(output):
    output = Path(output).expanduser()
    if output.exists() or output.is_symlink():
        raise FileExistsError('output path already exists; choose a new directory')
    if not output.parent.is_dir():
        raise FileNotFoundError('output parent directory must exist')
    texts = [(EXAMPLES / file).read_text(encoding='utf-8') for file, _, _ in CHAPTERS]
    analysis = tool('analyze', str(EXAMPLES / 'research-games.json'), '--team', '纸鸢队')
    bp = tool('check-bp', str(EXAMPLES / 'scenario.json'))
    training90, training60 = tool('train', '--minutes', '90'), tool('train', '--minutes', '60')
    if analysis['dataset_kind'] != 'synthetic' or bp['dataset_kind'] != 'synthetic':
        raise ValueError('the fixed demo requires explicit synthetic fixtures')
    payloads = {
        'analysis.json': json.dumps(analysis, ensure_ascii=False, indent=2) + '\n',
        'bp-check.json': json.dumps(bp, ensure_ascii=False, indent=2) + '\n',
        'training-90.json': json.dumps(training90, ensure_ascii=False, indent=2) + '\n',
        'training-60.json': json.dumps(training60, ensure_ascii=False, indent=2) + '\n',
        'index.html': page(texts, analysis, bp, training90),
        'demo-report.md': '# 塔罗王者赛训 五阶段离线演示\n\n完整虚构案例；预写对话与实际工具结果分别标注。\n\n' + '\n\n'.join(texts),
    }
    for filename in ('scenario.json', 'research-games.json', 'README.md', *(c[0] for c in CHAPTERS)):
        payloads[filename] = (EXAMPLES / filename).read_text(encoding='utf-8')
    raw_payloads = {name: value.encode('utf-8') for name, value in payloads.items()}
    manifest = {'schema_version': 1, 'version': '2.1.0', 'dataset_kind': 'synthetic',
                'network_requests': 0, 'model_requests': 0,
                'files': {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                          for name, raw in sorted(raw_payloads.items())}}
    raw_payloads['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    output.mkdir(mode=0o700)
    created = []
    try:
        for name, data in raw_payloads.items():
            path = output / name
            with path.open('xb') as stream:
                created.append(path)
                stream.write(data)
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        output.rmdir()
        raise
    return {'demo': str((output / 'index.html').resolve()), 'files': len(raw_payloads),
            'dataset_kind': 'synthetic', 'network_requests': 0, 'model_requests': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path('demo-output'))
    args = parser.parse_args(argv)
    try:
        result = build(args.out)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print('demo failed: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
