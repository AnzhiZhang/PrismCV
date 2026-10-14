<!-- markdownlint-disable MD033 MD041 -->

<div align="center">

<h1>Prism CV</h1>

<p><strong>One source, every CV.</strong></p>

<p>
  <a href="https://github.com/AnzhiZhang/PrismCV/blob/main/LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white">
  <a href="https://pypi.org/project/prismcv/"><img alt="PyPI" src="https://img.shields.io/pypi/v/prismcv?color=blue"></a>
  <a href="https://github.com/rendercv/rendercv"><img alt="RenderCV 2.8" src="https://img.shields.io/badge/RenderCV-2.8-blue"></a>
  <a href="https://github.com/AnzhiZhang/PrismCV/blob/main/README.zh-CN.md"><img alt="中文" src="https://img.shields.io/badge/README-%E4%B8%AD%E6%96%87-blue"></a>
</p>

</div>

Keep your whole career in one place and build every version of your CV from it: each language, academic and industry, and one tailored to each job. Edit an entry once and every version picks it up.

## How it works

```mermaid
flowchart LR
    C["content/<br/>every entry, written once,<br/>languages side by side"]
    T["targets/x.yaml<br/>which entries, in what order,<br/>what is reworded"]
    B["PrismCV<br/>assembles one YAML per language"]
    R["RenderCV<br/>typesets it into PDF"]
    P["out/x/*.pdf"]

    C --> B
    T --> B
    B --> R --> P
```

[RenderCV](https://github.com/rendercv/rendercv) typesets one YAML file into a PDF. PrismCV assembles that file from your content and a target; all layout is RenderCV's.

## Quick start

Requires Python 3.12+.

```sh
pip install prismcv
prismcv init my-cv                  # create a CV folder from a minimal template
cd my-cv
prismcv build --all                 # every target
prismcv build main --lang en        # one target, one language
prismcv build main --debug          # keep the generated RenderCV input
```

A CV folder holds `cv.yaml`, `design.yaml`, `content/` and `targets/`. Run `prismcv build` inside one, or point to one with `--root`. PDFs go to `out/<target>/`.

`prismcv init --example` creates a full bilingual example instead, using every feature below. Its Chinese version needs the [Noto Sans SC](https://fonts.google.com/noto/specimen/Noto+Sans+SC) font.

## Themes

Set `theme` in `design.yaml`.

![The example CV in nine themes: classic, engineeringresumes, sb2nov, moderncv, engineeringclassic, harvard, ink, opal and ember](https://raw.githubusercontent.com/AnzhiZhang/PrismCV/main/docs/themes.en.jpg)

## Content

`cv.yaml` holds your name and contact details and the section titles. Every file in `content/` holds entries keyed by an id; how you split them into files is up to you. Fields use [RenderCV's names](https://docs.rendercv.com).

Text that differs between languages maps language codes to text; anything else is written once. An excerpt from the example's [`content/experience.yaml`](https://github.com/AnzhiZhang/PrismCV/blob/main/src/prismcv/example/content/experience.yaml):

```yaml
brightwave-intern:
  company: { en: Brightwave Robotics, zh: 明波机器人 }
  location: { en: "Montreal, Canada", zh: 蒙特利尔 }
  start_date: 2025-05
  end_date: present
  highlights:
    - en: Wrote C++ drivers for an IMU
      zh: 编写惯性测量单元的 C++ 驱动
```

Use `zh: null` to leave a bullet out of one language. An id can also hold a list of entries (a group of skills), and an entry with only `text` is a paragraph (a profile).

## Targets

Each file in `targets/` is one version of the CV. `langs` defaults to every language, and `max_pages` warns when a PDF is longer. An excerpt from the example's [target tailored to one job](https://github.com/AnzhiZhang/PrismCV/blob/main/src/prismcv/example/targets/jobs/2026-10-15_example-data-engineer.yaml):

```yaml
langs: [en]
max_pages: 1
sections:
  profile:
    - text: Engineer who enjoys turning messy sensor data into reliable pipelines.
  work:
    title: Experience
    entries:
      - brightwave-intern@data
      - greenleaf-analyst:
          highlights:
            - Rewritten bullet for this role only
```

An item is an id, an id with fields to override, or an entry written inline. A variant such as `brightwave-intern@data` lives in `content/` and changes only the fields it lists, so it suits rewording you will reuse. `title` renames a section for this target.

## Languages

`languages` in `design.yaml` maps each code to a [RenderCV locale](https://docs.rendercv.com). To add one, add it there, put any settings it needs under its code (a font, a date format), and add its text to the content you use; the build lists anything missing.

## License

```text
MIT License

Copyright (c) 2026 Andy Zhang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
