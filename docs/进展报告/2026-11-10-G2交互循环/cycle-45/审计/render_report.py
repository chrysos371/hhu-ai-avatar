"""Small static MD/HTML report renderer; callers supply measured section content."""
import html
from pathlib import Path
import re


def render(out,title,subtitle,verdict,sections,css_source):
    css=re.search(r'<style>(.*?)</style>',Path(css_source).read_text(),re.S).group(1);e=html.escape
    md=['# '+title,'',subtitle,''];parts=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><style>'+css+'</style></head><body><main><h1>'+e(title)+'</h1><p class="meta">'+e(subtitle)+'</p><p class="verdict">'+e(verdict)+'</p>']
    for section in sections:
        md+=['## '+section['title'],''];parts+=['<section><h2>'+e(section['title'])+'</h2>']
        for paragraph in section.get('paragraphs',[]):md+=[paragraph,''];parts+=['<p>'+e(paragraph)+'</p>']
        if section.get('table'):
            headers,rows=section['table'];md+=['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']
            md+=['| '+' | '.join(c.replace('|','\\|').replace('\n','<br>') for c in row)+' |' for row in rows];md+=['']
            parts+=['<p class="scroll-hint">手机可横向滑动表格查看全部列。</p><div class="table-wrap" tabindex="0" aria-label="可横向滚动的数据表"><table><thead><tr>'+''.join('<th>'+e(c)+'</th>' for c in headers)+'</tr></thead><tbody>']
            parts+=['<tr>'+''.join('<td>'+e(c)+'</td>' for c in row)+'</tr>' for row in rows];parts+=['</tbody></table></div>']
        for label,url in section.get('links',[]):
            assert (out/url).resolve().is_file(),url
            md+=['- ['+label+']('+url+')'];parts+=['<p><a href="'+e(url,quote=True)+'">'+e(label)+'</a></p>']
        md+=[''];parts+=['</section>']
    parts+=['</main></body></html>'];(out/'系统审计与推进报告.md').write_text('\n'.join(md));(out/'系统审计与推进报告.html').write_text('\n'.join(parts)+'\n')
    return {'tables':sum(bool(s.get('table')) for s in sections),'links':sum(len(s.get('links',[])) for s in sections)}
