# リーダーのワークシート（公開用サイト）

静的サイトです。ビルド作業は不要で、このフォルダの中身をそのまま公開できます。

## 構成
- `index.html` … トップページ
- `style.css` … スタイル
- `downloads/` … ワークシート24種のPDF（1種ずつ）と、第1〜4弾のまとめPDF・PowerPoint
- `.nojekyll` … GitHub Pages用

## 公開前に決めること
- 運営者名や連絡先を載せる場合は、`index.html` のフッターに追記する
- 記入例は架空のサークル・架空のアイデアです。そのまま使うか、差し替える
- フォントは Google Fonts（Dela Gothic One / Zen Kaku Gothic New）を読み込んでいます

## GitHub Pages
1. 新しいリポジトリを作り、このフォルダの中身を直下に置いて push
2. Settings → Pages → Source を `Deploy from a branch`、`main` / `(root)` に設定
3. `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開される

## Cloudflare Pages
1. Workers & Pages → Create → Pages（Git連携、または Direct Upload）
2. Build command は空欄、Output directory は `/`
3. `https://<プロジェクト名>.pages.dev` で公開される。独自ドメインは Custom domains から追加
4. ダウンロード数の把握には、無料の Web Analytics が使える

## 更新のしかた
新しいワークシートは `downloads/` にPDFを追加し、`gen_site.py` を使わない場合は
`index.html` の一覧に `<li>` を1行足します。
# learder-worksheet
