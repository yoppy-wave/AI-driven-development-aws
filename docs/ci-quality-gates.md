# CI品質ゲート

Application CI/CDが全push、PRのopened/reopened/synchronize、手動実行を受け付けます。`reusable-ci.yml`のTest・Lint・Dependency・Security・Lambda modulesは独立して並列実行し、最後の`ci`が全結果を検証します。各ゲートの処理は`.github/workflows/reusable-quality-gate.yml`で管理します。

以前はRegression testsとApplication CI/CDがそれぞれ`run_regression.py`を実行していました。現在は1イベントにつき5ゲートを1組だけ実行します。同じ変更のpush（head）とPR（GitHubのマージ結果）は異なる検証対象なので、両方を検査します。

```text
Application CI/CD
  ci（再利用Workflow）
    Test ────────┐
    Lint ────────┤
    Dependency ──┼─→ ci / ci ─→ 既存のCDK diff → deploy
    Security ────┤       └────→ Regression tests / regression
    Lambda modules┘
```

`ci / ci`は`always()`で集約処理を実行し、5ゲートのfailure・cancelled・skipped・欠落をすべて失敗にします。各ゲートで実際に解決されたランタイムも検証し、成功後だけ既存のCDK有効化・リージョン・Preview監査・デプロイ有効化outputsを公開します。AWS jobの`needs: ci`は維持します。

`regression.yml`は再利用Workflowとして集約結果を検証する軽量な互換チェックです。caller名`Regression tests`とjob ID `regression`により、Rulesetsが要求する`Regression tests / regression`を維持します。`ci / ci`も変更しません。stg/prodのRulesets・PRポリシーは変更しません。

## Test

既存のプロジェクト検出、Pythonプロジェクトの`*_test.py`必須条件、Nodeプロジェクトのtest script必須条件を維持します。pytest、Jest、型チェック、build、CDK synthを実行します。Lintは専用ゲートへ移し、typecheck/buildの実体コマンドが同一なら1回だけ実行します。

## Lint

Pythonは固定バージョンのRuff CLIと`ruff.toml`を使います。未使用import・未定義名などの正しさに関わるE4/E7/E9/Fを検査します。TypeScript/JavaScriptはESLint CLIと`eslint.config.mjs`でrecommendedルールを適用し、警告も失敗にします。新しいNodeプロジェクトにもlint scriptが必要です。既存コードの大量整形を避けるため、全体のformat強制は今回導入していません。VS Code拡張は補助であり、CIの代替ではありません。

## Dependency

方針は`.github/quality/version-policy.json`で管理します。

| 区分 | 対象 | 判定 |
| --- | --- | --- |
| 更新追従 | Python 3.12系、Node.js 24系の実行バイナリ | 公式公開後の猶予が満了した版以上であること |
| 固定 | requirements-dev.txtのpytest/Ruffとrequirements-dev.lockの推移依存 | manifest・lock・インストール結果の完全一致、pip check |
| 固定 | package.jsonの全dependencies/devDependencies/optionalDependenciesとpackage-lock.json | 明示的な完全版指定、manifest・解決版一致、npm ci、npm ls |

固定パッケージには3日以内の更新を強制しません。現在の固定ポリシーでは`^`・`~`・`>=`などの範囲指定を許可せず、完全版との不一致を失敗にします。Nodeの推移依存はlockとnpmの整合性検査で管理します。Pythonプロジェクトを増やすときはfixed.pythonへmanifest/lockを追加します。Nodeプロジェクトは自動検出し、現在はnpm lockfile v2/v3を対象にしています。

ランタイムはパッチ固定文字列ではなく、setup-python/setup-nodeが`check-latest: true`で選んだ実バージョンを比較します。5ゲートすべてのsetup出力を集約jobでも検証するため、Dependencyだけ新しいランタイムでも成功にはなりません。Dev Containerの広い指定（Python 3.12、Node 24）とポリシーの一致も確認します。CIがDev Containerの既存イメージを自動更新するわけではありません。手元の実行環境でDependencyゲートを実行すれば、その実バージョンを検査できます。イメージが古ければ再ビルドが必要です。

公式データソースは次の2つです。

- Python: [python.org releases API](https://www.python.org/api/v2/downloads/release/?is_published=true)。`name`、`release_date`、`is_published`、`pre_release`を使用します。3.12系の公開済み正式版だけを比較します。
- Node.js: [公式nodejs/node Releases API](https://api.github.com/repos/nodejs/node/releases?per_page=100)。`tag_name`、`published_at`、`prerelease`、`draft`を使用します。24系の公開済み正式版だけを比較します。Actionsでは読み取り用の既存GITHUB_TOKENをこの公式GitHub APIへの認証にだけ使います。

猶予は72時間で、境界時刻に達したら更新必須です。両方ともタイムゾーン付きの公式公開時刻を使用します。Node.jsのdistribution indexは日付精度なので使いません。新しい版が猶予内でも、それ以前の猶予切れ更新は引き続き必須です。Python 3.13やNode 26への系統変更は要求せず、選択系統外での実行は失敗にします。

公式APIの取得失敗・不正な応答・該当正式版の欠落は`RELEASE_SOURCE_ERROR`、古いランタイム・固定版やlockの不一致は`VERSION_POLICY_ERROR`として区別します。外部APIを取得できない場合は、未確認のまま成功にしません。時刻とAPI応答は単体テストで固定・Mock化します。

## Security

Python標準`ast`と既存のTypeScript Compiler APIを使用します。Git管理ファイルと未追跡・非ignoreファイルのPython、JavaScript、TypeScriptソースを解析します。文字列中に書かれたコードを単純検索しているわけではありません。

- Pythonのprint、logging、logger/logおよびgetLoggerで得た変数のログメソッドを対象にします。loggingのimport aliasや直接importしたログ関数にも対応します。
- JavaScript/TypeScriptのconsole、logger/log、createLogger/getLogger等の変数、既知のロガーmoduleからimportしたログ関数を対象にします。
- 引数の識別子、属性、要素参照、辞書/オブジェクトのキー、補間文字列、展開、getによるキー取得などを構造として調べます。password、token、API key、Authorization、credentials等を直接渡す呼び出しを拒否します。
- 通常の完了メッセージ、request ID、明示的なマスク値は許可します。語彙・安全なメタデータ名・マスク値は`.github/quality/log-policy.json`で管理します。
- 違反はファイル名・行番号・理由を表示して非ゼロ終了します。機密値やソース全文は診断に含めません。構文解析エラーも失敗です。

これは直接的な機密ログ引数の検査です。任意の別名への代入、関数間・ファイル間データフロー、独自ロガーwrapper、計算されたキー、実行時に生成された秘密値を完全に追跡するものではありません。一般名の変数に隠れた機密値は見逃し得ます。一方、機密語を含む非機密変数は誤検知し得るため、明確な名前への変更や限定的なポリシー調整が必要です。依存脆弱性監査や汎用secret scanningを代替しません。

## ローカル検証

開発コンテナのPython仮想環境を有効にして実行します。

```bash
python .github/scripts/run_regression.py
python .github/scripts/run_lint.py
python .github/scripts/check_dependencies.py
npm ci --ignore-scripts
python .github/scripts/check_security.py
```

ローカルで同じnode_modulesを共有する場合は、インストールを伴う各コマンドを同時実行しません。CIでは各ジョブが独立したrunnerで動きます。意図的なpytest失敗、Ruff/ESLint違反、機密ログ、猶予境界値、固定版不一致、skipped/cancelledゲートをテストで確認します。

AWS CDK・Preview Environment・各環境デプロイは引き続き初期無効です。品質チェックは実AWSへのdiff/deploy/deleteを行いません。Stack命名・cleanup・GitHub Actions編集用VS Code拡張・コンテナ通信制御は変更しません。
