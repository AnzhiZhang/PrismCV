# CV

一份内容，生成所有版本的简历。内容放在 `content/`，每个版本是 `targets/` 里的一个小文件，`build.py` 把两者拼成 RenderCV 的输入文件，再由 RenderCV 排版成 PDF。

## 使用

用 conda 的 `rendercv` 环境（Python 3.12 以上）。第一次需要装依赖：

```sh
conda activate rendercv
pip install -r requirements.txt
```

中文版用 Noto Sans SC（思源黑体），需要先安装到系统：从 [Google Fonts](https://fonts.google.com/noto/specimen/Noto+Sans+SC) 下载，安装解压后 `static/` 里的字体文件，不要装可变字体（`VariableFont`），Typst 对它支持不完整。

之后：

```sh
conda activate rendercv
python build.py industry                              # 生成一个版本
python build.py jobs/2026-10-15_example-data-engineer    # 生成一个岗位版本
python build.py --all                                 # 生成全部版本
python build.py industry --lang en                    # 只生成英文
python build.py industry --debug                      # 保留中间文件，排查用
```

PDF 生成在 `out/<版本>/` 下。排查问题时加 `--debug`，会在 PDF 旁边留下拼好的 RenderCV 输入文件（`.yaml`）和 Typst 源文件（`.typ`）。

## 目录

```
content/          所有内容（按板块分文件，文件名随意，id 全局唯一）
  header.yaml     姓名、联系方式
  sections.yaml   板块标题的中英对照
targets/          每个版本一个文件
  jobs/           岗位定制版本，命名：日期_公司_岗位.yaml
design.yaml       排版设置（字体、A4、中文日期格式等）
```

## 写内容

**中英文规则**：写纯文本表示中英相同，写成 `{ en: ..., zh: ... }` 表示分语言。

```yaml
brightwave-intern:
  company: { en: Brightwave Robotics, zh: 明波机器人 }
  position: { en: Embedded Software Intern, zh: 嵌入式软件实习生 }
  location: { en: "Montreal, Canada", zh: 蒙特利尔 }# 含逗号的文字要加引号
  start_date: 2025-05
  end_date: present                                # 中文版自动显示“至今”
  highlights:
    - en: Wrote C++ drivers for an IMU
      zh: 编写惯性测量单元的 C++ 驱动
```

- 某种语言不需要某条 bullet：写 `zh: null`。
- 两种语言条数差别大：`highlights: { en: [...], zh: [...] }`。
- 一个 id 也可以对应一组条目（列表），比如 `skills.yaml` 里的技能分组。
- 只有 `text` 字段的条目是一段文字，用于个人简介。
- 条目的字段名就是 RenderCV 的字段名，见 [RenderCV 文档](https://docs.rendercv.com)。

## 写版本

```yaml
langs: [en, zh]     # 生成哪些语言，默认两种都生成
max_pages: 1        # 超过页数会警告，不写则不限
sections:           # 板块顺序就是输出顺序
  profile: [profile-industry]
  education: [meng, bsc]
  work: [brightwave-intern, greenleaf-analyst]
```

板块的 key 要在 `content/sections.yaml` 里有标题。

## 定制

```yaml
sections:
  profile:
    - text: 直接写一段只给这个岗位用的简介
  work:
    title: Experience               # 只对这个版本改标题
    entries:
      - brightwave-intern@data      # 引用变体
      - greenleaf-analyst:          # 覆盖字段，没写的沿用原文
          highlights:
            - Rewritten bullet for this role
```

**变体**：在 content 里写 `原id@名字`，自动继承原条目，只写要改的字段（也可以显式写 `base: 原id`）。只用一次的改写放在 target 里覆盖；会用到两次以上就做成变体。约定：日期或机构变了就新建条目，不要用变体。

## 检查

build.py 会报告：id 重复、id 不存在、某种语言缺少文本、同一板块混入不同类型的条目、板块缺少标题，以及页数超过 `max_pages`。日期格式等由 RenderCV 自己校验。

## 注意

- 投递版本的 PDF 自己另存。job 文件引用的是 content，以后 content 改了，重新生成的内容也会变。
- RenderCV 版本固定在 `requirements.txt`，升级前先确认 YAML 格式是否有变化。
- bullet 里不要写 ` - `，RenderCV 会把它当成子列表。
