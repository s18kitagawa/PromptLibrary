# stock-screening

Pre-screen a photo archive for **Adobe Stock** submission candidates, one capture year at a
time. Any folder layout works (flat, `Camera/`, `Trips/Kyoto/`, `YYYY/YYYY-MM-DD/`, ...):
files are selected by the year they were taken, not by where they are stored.

1. **Automatic screening** - groups RAW+JPEG pairs and edited derivatives, checks the
   Adobe Stock resolution limits (4-100 MP), rejects out-of-focus and badly exposed frames,
   and keeps only the sharpest frame of each burst.
2. **Visual review** - renders numbered contact sheets that a person (or Claude, via
   [`SKILL.md`](SKILL.md)) reviews; decisions are recorded per file as
   `candidate` / `review` / `reject`.
3. *(planned)* A Lightroom Classic plug-in that turns the candidate list into a collection,
   from which you publish via Lightroom's built-in Adobe Stock publish service.

日本語の説明は [下部](#日本語) にあります。

## Privacy by design

The code never stores results next to itself:

- All results go to an **output folder you choose**, which must be outside this repository
  and outside the photo archive - the tool refuses to run otherwise.
- Results store paths **relative to the archive root**; absolute paths appear only in
  `export_*.txt`, and only when you pass `--path-prefix`.
- `.gitignore` additionally excludes `config.local.toml`, `*.csv`, `*.jsonl` and `sheets/`.
- Your personal paths live in `config.local.toml` (git-ignored), environment variables,
  or CLI flags - never in `config.toml`.

## Requirements

- macOS or Linux, Python 3.10+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Folder layout: anything under the archive root; no year folders needed
- Supported: RAW (`arw dng nef cr2 cr3 raf orf rw2 pef srw`), `jpg/jpeg/tif/tiff/png`.
  Videos are listed and rejected. HEIC is not supported.

## Setup

```bash
git clone <this repo> stock-screening && cd stock-screening
uv sync                                  # creates .venv and installs dependencies
cp config.local.example.toml config.local.toml
# edit config.local.toml: photos_root and out_dir
```

Instead of `config.local.toml` you can use `STOCK_SCREENING_PHOTOS_ROOT` /
`STOCK_SCREENING_OUT_DIR`, or `--photos-root` / `--out-dir` on every command.

## Usage

```bash
uv run stock-screening scan   --year 2019   # analyze files (cached; re-run to resume)
uv run stock-screening select --year 2019   # apply rules -> screen.csv
uv run stock-screening sheets --year 2019   # contact sheets of passing files
uv run stock-screening mark   --year 2019 --ids 1-4,9 --decision candidate
uv run stock-screening mark   --year 2019 --ids 5 --decision review --flags people,logo --note "..."
uv run stock-screening status --year 2019   # progress, unreviewed IDs
uv run stock-screening export --year 2019 --decision candidate --path-prefix /Users/you/Pictures/RAW_Photos
```

- `--year` is the **capture year**: the EXIF date (DateTimeOriginal → DateTimeDigitized →
  DateTime), or the file modification time (mtime) when a file has no EXIF date.
  Which one was used is recorded as `date_source` (`exif` / `mtime`) in `screen.csv`, and
  `status` shows how many files of the year were dated by mtime.
- `scan` works in two steps: (1) read the capture date of every new or changed file in the
  whole archive (cheap), (2) analyze the previews of the files of `--year` only.
  The first run reads the entire archive, so it may need several runs.
- `scan --time-budget N` stops after N seconds with exit code 3; run it again to continue.
  The cache is append-only, so interruption is always safe.
- `select` is cheap: change thresholds and re-run without rescanning.
- `sheets` skips files that already have a decision (`--include-reviewed` to show all).
  Decisions are keyed by file path, so renumbered tiles never break earlier reviews.
- Flags: `people logo text landmark artwork private focus noise similar composition`.

## Output layout

```
<out_dir>/cache.jsonl     capture dates + metrics for the whole archive (append-only)
<out_dir>/<YYYY>/
├─ screen.csv             pass/reject + reasons for every file of the year
├─ sheets/sheet_NNN.jpg   numbered contact sheets
├─ sheets/index.csv       tile ID -> file
├─ review.csv             decisions (candidate / review / reject), flags, notes
└─ export_<decision>.txt  file list for Lightroom
```

## How screening works / tuning (`config.toml`)

All metrics are computed on the JPEG preview embedded in each RAW (fast; no demosaicing).

| Rule | Default | Notes |
|---|---|---|
| Excluded folders | `exclude_globs = []` | globs on the path relative to the archive root, e.g. `["*.lrdata", "Exports"]`; a matching folder is skipped entirely. Hidden files/folders are always skipped |
| Copies & derivatives | keep one per frame | files in the same folder with the same base name: `LRG_`/`ORG_` copies and `-hdr`, `-強化-NR`, `-Enhanced-NR`, `-Edit` variants are grouped; `prefer_derivative = true` keeps the edited version |
| Resolution | 4-100 MP | Adobe Stock limits |
| Sharpness | `min_sharpness = 100` | max Laplacian variance over a 4x4 grid on a 1024 px preview, so shallow-DoF shots with a sharp subject pass |
| Exposure | highlights >25% clipped or mean >235; mean <12 | shadows deliberately loose so night scenes pass |
| Bursts | within 30 s and pHash distance <= 12 | sharpest frame kept; only files with an EXIF date |

Override any value in `config.local.toml`. If you change metric definitions in code,
bump `METRICS_VERSION` in `metrics.py` to invalidate caches.

## Tests

```bash
uv run python tests/test_logic.py
```

## Using with Claude Cowork

After this one-time setup, you only need to ask Claude to screen a given year.

1. In the Claude app, open **Customize → Skills → Add → Upload skill** and register `SKILL.md` as a skill.
2. Create a new project (any name).
3. Connect these three local folders to the project as context:
   1. this repository (`stock-screening`)
   2. the folder containing the photos to screen (e.g. `RAW_Photos`)
   3. the output folder for screening results (e.g. `stock_screening_out`; it must be outside the other two)

Setup is complete. Start a Cowork session in the project and ask, for example,
*"Screen 2020 for Adobe Stock"* (or 「2020年をスクリーニングして」).

- On the first run Claude installs the dependencies, which takes a little longer (network access required).
- The first screening also reads the capture dates of the whole archive, so Claude runs `scan`
  several times; later years reuse those dates.
- If a session is interrupted, ask for the same year again; it resumes where it left off.
- In Cowork the commands run in a Linux VM; the skill places the virtualenv in
  `$HOME/.venvs/stock-screening`, so no Linux binaries end up in this folder.

## Limitations

- Automatic checks are coarse and preview-based; they remove obvious failures only.
  Final selection, model/property releases and Adobe Stock's content policies remain your
  responsibility. Passing this screening does not mean Adobe will accept an image.
- Not affiliated with or endorsed by Adobe.

## License

No license has been chosen yet; all rights reserved by the author until one is added.

---

## 日本語

写真アーカイブから、**Adobe Stock** に投稿できそうな写真を撮影年単位で絞り込むツールです。フォルダ構成は自由です（フラット、`Camera/`、`旅行/京都/`、`YYYY/YYYY-MM-DD/` など）。保存場所ではなく撮影日時の年で対象を選びます。

1. **自動スクリーニング**：RAW+JPEG や編集後の派生ファイルを 1 枚にまとめ、Adobe Stock の解像度要件（4〜100MP）を確認し、ピンボケ・露出不良・連写の重複を除外します。
2. **目視選別**：番号付きのコンタクトシートを作成し、人（または [`SKILL.md`](SKILL.md) に従う Claude）が `candidate` / `review` / `reject` を記録します。
3. *（予定）* 候補リストを Lightroom Classic のコレクションにするプラグイン。そこから Lightroom 標準の Adobe Stock 公開サービスで送信します。

### プライバシー設計

- 結果は**自分で指定した出力フォルダ**にのみ保存されます。出力先がこのリポジトリ内や写真アーカイブ内の場合は実行を拒否します。
- 結果ファイルに記録するのはアーカイブからの**相対パス**です。絶対パスは `export --path-prefix` を指定した場合のみ出力されます。
- 個人のパスは `config.local.toml`（git 管理外）・環境変数・コマンド引数で指定し、`config.toml` には書きません。

### セットアップと使い方

```bash
uv sync
cp config.local.example.toml config.local.toml   # photos_root と out_dir を編集
uv run stock-screening scan   --year 2019
uv run stock-screening select --year 2019
uv run stock-screening sheets --year 2019
uv run stock-screening mark   --year 2019 --ids 1-4 --decision candidate
uv run stock-screening status --year 2019
uv run stock-screening export --year 2019 --path-prefix /Users/you/Pictures/RAW_Photos
```

- `--year` は**撮影年**です。EXIF の撮影日時（DateTimeOriginal → DateTimeDigitized → DateTime）を使い、ない場合はファイルの更新日時（mtime）で代用します。どちらを使ったかは `screen.csv` の `date_source` 列（`exif` / `mtime`）に記録され、`status` には対象年のうち mtime で判定した件数が表示されます。
- `scan` は 2 段階で動きます。(1) アーカイブ全体の新規・変更ファイルについて撮影日時だけを読み（軽量）、(2) 対象年のファイルだけプレビューを解析します。初回はアーカイブ全体を読むため、何度か再実行が必要になることがあります。
- `scan` は中断しても再実行すれば続きから処理します（`--time-budget` で時間制限可）。
- 除外したいフォルダ（Lightroom のプレビュー、書き出し先など）は `config.local.toml` の `[inventory]` に `exclude_globs = ["*.lrdata", "Exports"]` のように指定します（写真フォルダからの相対パスの glob。一致したフォルダは中身ごと除外）。隠しファイル・隠しフォルダは常に除外されます。
- 同じフォルダ内で基本ファイル名が同じもの（RAW+JPEG、`LRG_` コピー、`-Enhanced-NR` などの派生）は 1 枚にまとめます。
- しきい値は `config.local.toml` で上書きし、`select` だけ再実行すれば反映されます。

### テスト

```bash
uv run python tests/test_logic.py
```

### Claude Cowork での実行手順

次のセットアップを一度おこなえば、あとは年を指定して依頼するだけでスクリーニングを実行できます。

1. Claude アプリで「カスタマイズ」→「スキル」→「追加」→「スキルをアップロード」を開き、`SKILL.md` をスキルとして登録します。
2. プロジェクトを新規作成します（プロジェクト名は任意）。
3. プロジェクトのコンテキストとして、次の 3 つのローカルフォルダを接続します。
   1. このリポジトリのフォルダ（`stock-screening`）
   2. スクリーニングしたい写真が入っているフォルダ（例：`RAW_Photos`）
   3. スクリーニング結果の出力フォルダ（例：`stock_screening_out`。上の 2 つのフォルダの外に作成してください）

これでセットアップは完了です。作成したプロジェクトで Cowork のセッションを開始し、「2020年をスクリーニングして」のように年を指定して依頼してください。

- 初回は Claude が必要なライブラリをインストールするため、少し時間がかかります（ネットワーク接続が必要です）。
- 初回のスクリーニングではアーカイブ全体の撮影日時を読むため、Claude が `scan` を何度か再実行します。2 年目以降はその結果を再利用します。
- 途中で中断しても、同じ年を再度依頼すれば続きから再開します。

### 注意

自動判定はプレビュー画像による簡易的なものです。最終的な選定、モデル／プロパティリリース、Adobe Stock のコンテンツポリシーへの適合は利用者の責任で確認してください。本ツールは Adobe とは無関係です。
