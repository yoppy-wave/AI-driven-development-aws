# GitHubリポジトリの初回設定

この文書は、テンプレートから作成したプロジェクトを利用可能にするために、**プロジェクト管理者**が一度行う設定をまとめたものです。開発者個人の端末準備は[開発者セットアップ](developer-setup.md)、日々の実装・PR・AI Issueの利用は[開発ガイド](development-guide.md)を参照してください。

リポジトリ内の設定ファイルをコミットしただけでは、GitHubやAWSの管理画面で行う保護・権限・認証の設定は有効になりません。ここでは両者を明確に区別します。

## 1. プロジェクトとアクセスの準備

### GitHub Organizationとリポジトリ

1. チーム開発では、Organization配下にリポジトリを作成します。個人開発では個人アカウント配下でも利用できます。
2. 公開範囲（public / private / internal）は、ソースコード、Issue、Actionsログ、利用するSecretsの取り扱い方針に合わせて決めます。公開リポジトリでもSecretsの値は公開されませんが、workflowやログに秘密情報を出力しない運用が必要です。
3. テンプレートから作成した場合も、不要な履歴や設定を引き継いでいないかを確認します。
4. 初期段階の個人開発では、現在の既定ブランチである`main`を維持できます。チーム開発へ移行する時点で、以下のブランチ構成と保護を有効化します。

### メンバー・Team・権限

- **個人開発**: リポジトリ所有者だけで運用できます。管理権限を他者へ安易に付与しません。
- **チーム開発**: Organizationで少なくとも開発者、Product Owner（PO）、リリース責任者を分けます。Teamを使う場合は、CODEOWNERSで参照できるvisible Teamにします。
- リポジトリ管理、Rulesetのbypass、Environmentの承認、AWS IAM管理は必要最小限の担当者だけに付与します。通常の開発者には、PR作成・レビューに必要な権限を付与します。
- 外部協力者には、必要な期間と範囲に限った権限を設定します。fork PRはpreview環境の対象外です。

## 2. ブランチとPR保護

### チーム開発のブランチ構成

チーム開発では次の構成を使用します。

```text
prod                    本番相当の安定ブランチ
└─ stg                  開発内容を統合・検証するブランチ
   └─ feature/<内容>    個別開発ブランチ
```

- 実装は`stg`から作成した`feature/<内容>`または`fix/<内容>`で行います。
- 日常の変更は`feature/*`または`fix/*`から`stg`へのPRで取り込みます。
- リリース可能なまとまりで`stg`から`prod`へのPRを作成します。
- `prod`と`stg`はGitHub上またはローカルGitで作成してリモートへpushします。`prod`を既定ブランチにするかは、チームの移行方針に合わせて決めます。

現在の個人開発での`main`中心の進め方は[開発ガイド](development-guide.md#個人開発main中心)を参照してください。

### リポジトリ内の設定ファイル

次のファイルは、チーム開発でGitHubへインポート・有効化するための**disabled状態のテンプレート**です。ファイルだけではGitHubの保護は有効になりません。

```text
.github/rulesets/stg.json
.github/rulesets/prod.json
.github/rulesets/prod-merge-actors.json
.github/CODEOWNERS.example
```

- `stg.json`: PR必須、作成者以外の開発者1人以上の承認、CI、会話解決、force push・削除の禁止。
- `prod.json`: PR必須、POのCODEOWNERS承認、CI、会話解決、force push・削除の禁止。
- `prod-merge-actors.json`: `prod`の更新者をリリース責任者に限定するための**Restrict updates**のみ。
- `CODEOWNERS.example`: POにレビューを要求するための雛形。実ファイル`.github/CODEOWNERS`はまだ存在しません。

`stg.json`と`prod.json`に**Restrict updates**を入れないことが重要です。品質ゲートと更新者制限を分離することで、リリース責任者に更新者制限だけを通過させても、PO承認やCIを回避させません。

### GitHub管理画面で有効化する設定

チーム開発へ移行するときは、以下を順に実施します。

1. `prod`と`stg`を作成する。この時点ではRulesetを有効化しない。
2. `.github/CODEOWNERS.example`を`.github/CODEOWNERS`へコピーし、`@YOUR_ORG/product-owners`をPOのvisible TeamまたはGitHubユーザーに置換する。
3. **CODEOWNERSを含むコミットを先に`prod`へ配置する。** `prod` RulesetでCODEOWNERS承認を要求する前に、対象ブランチ上にこのファイルが必要です。
4. `stg` / `prod`宛てのテストPRを作成し、必須チェックが表示・成功することを確認する。
5. GitHubの **Settings → Rules → Rulesets** で3つのJSONをインポートし、直後は`disabled`のままであることを確認する。
6. `prod-merge-actors.json`のbypass listにリリース責任者のユーザーまたはTeamを追加し、bypass modeを **For pull requests only** にする。直接pushを許す **Always allow** は選ばない。
7. `stg` Rulesetを有効化し、PR・他者承認・CI・会話解決を満たさない変更がマージできないことを確認する。
8. `prod.json`と`prod-merge-actors.json`を有効化し、PO以外の承認だけではマージできず、必要な品質ゲートを満たしたPRをリリース責任者がマージできることを確認する。

#### 必須ステータスチェック

Rulesetの必須チェックには、次のcheck contextを指定します。

| check context | 定義元 |
| --- | --- |
| `Regression tests / regression` | `.github/workflows/regression.yml` |
| `Pull request policy / validate` | `.github/workflows/pull-request-policy.yml` |

品質ゲートは全ブランチへのpushとPRで実行されます。Test・Lint・Dependency・Security・Lambda modulesを並列実行し、`ci / ci`で集約します。Rulesets用の`Regression tests / regression`は同じ集約結果を検証する互換チェックとして維持します。詳しくは[CI品質ゲート](ci-quality-gates.md)を参照してください。PRポリシーは、`prod`宛てを同一リポジトリの`stg`からだけ、`stg`宛てを`feature/*`または`fix/*`からだけ許可します。

## 3. GitHub Actions、AI Issueワークフロー、Secrets

### GitHub Actionsの実行権限

GitHubの **Settings → Actions → General** で、リポジトリ方針に沿ってActionsを許可します。`ai-coding.yml`がドラフトPRを作成するには、**Workflow permissions**でGitHub Actionsによるプルリクエスト作成を許可します。

workflowは必要な権限をYAMLで明示していますが、リポジトリ設定でより強い制限を掛ける場合は、CI、AI Issueワークフロー、CDK workflowが必要とする権限と両立することをテストしてください。

### AI Issueワークフローの有効化

`ai-question.yml`と`ai-coding.yml`は、既定ブランチに存在すると利用できます。`ai-coding.yml`は対応するラベルをIssueへ付与したとき、または同一リポジトリのPRへ信頼済みユーザーが`/cline fix`とコメントしたときに起動します。PRの変更ファイルはデータとしてのみ読み、PRブランチをcheckout・実行しません。`ai-question.yml`は`ai-question`ラベルに加え、OWNER、MEMBER、COLLABORATORがIssueコメントで`@cline`を付けたときにも起動します。利用する場合はGitHub管理画面で次を設定します。

| 種別 | 名前 | 用途 | 必須性 |
| --- | --- | --- | --- |
| Repository secret | `AZURE_OPENAI_API_KEY` | Azure OpenAIのAPIキー | AI Issueワークフローを使う場合は必須 |
| Repository variable | `AZURE_OPENAI_ENDPOINT` | Azure OpenAI v1のベースURL（例：`https://<resource>.openai.azure.com/openai/v1/`） | 必須 |
| Repository variable | `AZURE_OPENAI_DEPLOYMENT` | Azure上に作成したモデルデプロイ名 | 必須 |
| Repository secret | `AI_CODING_PR_TOKEN` | AI作成PRの後続CIを自動実行したい場合のPAT | 任意 |

- `AI_CODING_PR_TOKEN`を使う場合は、`contents: write`と`pull-requests: write`だけを必要範囲として付与します。未設定時は`GITHUB_TOKEN`を使います。
- GitHub上で`ai-question`と`ai-coding`ラベルを作成します。
- Azure OpenAIのベースURLは`/openai/v1/`まで含め、デプロイ名をClineのモデルIDとして指定します。v1 APIでは日付付きAPIバージョンは不要です。リソース側で利用上限を設定し、信頼できる担当者だけが`ai-coding`ラベルを付与できる運用にします。APIキー、PAT、AWS認証情報をリポジトリやStack Outputへ保存しません。
- AI Issueワークフローの利用方法・制約は[開発ガイド](development-guide.md#issueからaiを利用する)を参照してください。

## 4. GitHub EnvironmentsとAWS OIDC

### 現在の状態

`.github/cicd/application.json`がCI/CDの有効化契約です。現在は`ci.enabled`だけが`true`で、AWS CDK、PR preview、development / staging / productionへのデプロイはすべて`false`です。この状態ではAWS認証、`cdk deploy`、`cdk destroy`はworkflowから実行されません。

AWS CDKのStack構成、previewの安全策、cleanupの設計は[AWS CDKアーキテクチャ](aws-cdk-architecture.md)を参照してください。

### AWS・GitHub管理画面での準備

AWSデプロイを有効化する前に、プロジェクト管理者は次を準備します。

1. 対象環境のAWSアカウント、リージョン、Stack名、変更・削除対象、データのバックアップ・復旧方法を決める。プレビュー監査を有効にする場合は、読み取り専用の`preview-audit` Environmentと専用OIDCロールも準備する。
2. GitHub Actions OIDC用のIAM identity providerと、環境ごとに最小権限のIAM Roleを作成する。アクセスキーは使わず、Role ARNをソースやOutputへ書かない。
3. GitHubの **Settings → Environments** で`preview`、`preview-audit`、`development`、`staging`、`production`を作成する。対象のRole ARNを、各Environmentの`AWS_ROLE_TO_ASSUME` **Environment Secret**として設定する。`preview-audit`にはSTS caller identity確認とCloudFormationのStack一覧・詳細参照だけを許可する専用Roleを使う。
4. `preview`、`preview-audit`、`staging`、`production`にはrequired reviewersを設定する。productionには承認者と必要なdeployment branch policyも設定する。developmentも組織方針に応じて承認・ブランチ制限を設定する。
5. `application.json`で、必要な`cdk.enabled`、`previewEnvironmentEnabled`、`previewOrphanAuditEnabled`、`deployments`だけを明示的に`true`にする。監査はStackを報告するだけで削除しない。
6. 承認済みの範囲で、対象Stackと環境を限定してCI/CDの挙動を確認する。

再利用workflowは`workflow_call.secrets`で必要なSecret名を明示し、callerも`AWS_ROLE_TO_ASSUME`だけを明示的に渡します。jobに割り当てたGitHub Environmentの同名Secretが優先されます。

## 5. 開発者の追加・削除

### 追加時

- Organizationメンバーまたは外部協力者として招待し、必要なTeamと最小権限を割り当てる。
- チーム開発では、開発ガイド、PRレビュー責任、対象ブランチ、AI Issueラベルの利用権限を共有する。
- AWSコンソールや長期アクセスキーを開発者へ配る必要はありません。必要なクラウド操作はEnvironmentで保護したGitHub Actions OIDC経由に限定します。

### 削除・異動時

- Organization、Team、リポジトリ協力者、CODEOWNERS、Ruleset bypass list、Environment reviewersから対象者を外す。
- 個人に発行したPAT、APIキー、外部サービスのアカウント・トークンを失効またはローテーションする。
- AWS IAM Roleの信頼ポリシー、IAM Identity Centerなど、対象者に紐付くアクセス経路を見直す。
- 所有中のIssue、PR、レビュー待ち、リリース責任を別担当へ引き継ぐ。

## 設定完了チェックリスト

### 全プロジェクト共通

- [ ] リポジトリの所有者と公開範囲を決定した
- [ ] 管理者と通常開発者の権限を最小権限で設定した
- [ ] `main`または採用する既定ブランチを確認した
- [ ] GitHub Actionsの実行方針とWorkflow permissionsを確認した
- [ ] AI Issueワークフローを使う場合、必要なラベルとSecrets / variablesを設定した
- [ ] APIキー、PAT、AWS認証情報をリポジトリへ保存していない

### チーム開発へ移行する場合

- [ ] `prod`と`stg`を作成した
- [ ] `.github/CODEOWNERS`を`prod`へ配置した
- [ ] `stg` / `prod`宛てのテストPRで必須チェックの成功を確認した
- [ ] `stg`用Rulesetを有効化した
- [ ] `prod`用品質ゲートRulesetを有効化した
- [ ] `prod`用更新者制限Rulesetを有効化し、リリース責任者をPR限定bypassに設定した
- [ ] `stg`と`prod`への直接pushが拒否されることを確認した
- [ ] `feature/* → stg`、`stg → prod`のPR運用をチームで共有した

### AWS CDKを有効化する場合

- [ ] 対象AWSアカウント、リージョン、Stack、変更・削除対象、復旧方法を確認した
- [ ] GitHub Actions OIDCと環境別・最小権限のIAM Roleを設定した
- [ ] `preview`、`development`、`staging`、`production` Environmentと`AWS_ROLE_TO_ASSUME`を設定した
- [ ] `preview`、`staging`、`production`のrequired reviewersを設定した
- [ ] `.github/cicd/application.json`で必要な機能だけを`true`にした
- [ ] 有効化対象のworkflowを、承認済みの環境で確認した
