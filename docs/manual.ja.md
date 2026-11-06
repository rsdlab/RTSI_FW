# RT System Integration Framework（RTSI-FW）利用マニュアル

[README（日本語）](../README.ja.md) | [English README](../README.md)

> 対象：v1.0（`main`）

## 1. 概要
RTSI-FWは，RoIS 2.0に準拠したロボットシステム運用・管理フレームワークである．ロボット設定ファイルとシナリオファイルを読み取り，必要なパッケージの収集，ビルド，ネットワーク設定，モジュール起動，Service Applicationの実行を自動で行う．

```text
Systemoperate.py
  ├─ ロボット設定ファイル（ROBOT.yaml）
  ├─ シナリオファイル（scenario.yaml）
  ├─ Wasanbon / Wasanbon Web Framework
  └─ Service Application（ROS1 / ROS2）
       └─ common_hri_ros1 / common_hri_ros2
            └─ ロボット固有 Action ノード
                 └─ ロボット実機・シミュレータ
```

## 2. 開発環境
- 開発言語：Python
- OS: Ubuntu 20.04 / 22.04
- ROS: ROS1 noetic / ROS2 humble
- RTミドルウェア:OpenRTM-aist-2.0

## 3. 事前準備
使用するPCにはROS,RTMなどの必要なミドルウェア，[Wasanbon](https://github.com/rsdlab/wasanbon)，[Wasanbon_webframework](https://github.com/rsdlab/wasanbon_webframework)を導入してあるものとする．

### 3.1 リポジトリの取得
必要パッケージを取得する．
```bash
cd ~
git clone https://github.com/rsdlab/RTSI_FW.git
cd RTSI_FW
```
＊現在の実装では，ロボット設定ファイルとシナリオファイルの参照先を $HOME/RTSI_FW/ としているため，リポジトリはホームディレクトリ直下に配置する．

### 3.2 環境変数の設定
`Systemoperate.py`の起動時には`ROS_WS`と`RTM_WS`を参照します。対象環境に合わせて両方を定義します。

```bash
# ROS2時の例（実際のワークスペースに合わせて変更）
export ROS_WS="$HOME/colcon_ws"
export RTM_WS="$HOME/rtm_ws"
source /opt/ros/humble/setup.bash
# ビルド済みの場合：source "$ROS_WS/install/setup.bash"
```

## 4. ロボット設定ファイルの記述
ロボット固有の設定を記載する．
Systemoperate.py実行時参照するファイルとして利用させるものである．

| 項目 | 説明 |
| --- | --- |
| `collect` | `rtm`、`engine`、`apt`、`pip`、`git`などの取得対象 |
| `setup` | 初期化処理（`actions`）と完了確認（`checks`） |
| `run` | PCごとに起動する`system`と`module` |
| `network` | PCの識別ID、接続先、ローカルPC判定 |
| `ros.version` | `1`：ROS1、`2`：ROS2 |
| `ros2.domain_id` | ＊ROS2の場合のみ必要＊　ROS2で用いるDomain ID |

### 4.1 `collect`
`engine`には使用するHRIパッケージ名を指定する．`git`にはパッケージの取得先を記載する．取得項目がない場合は空リスト [] または null を要素とするリストを指定する．

### 4.2 `setup`
`setup`では，事前に完了させておきたい処理（サーボONなど）を記載する．各工程の`name`と`package`、起動する`actions`、完了判定する`checks`が記載できる．

| 項目 | 説明 |
| --- | --- |
| `name` | 処理の名前 |
| `package` | 処理するパッケージ名 |
| `actions` | `controller`: 処理するPCのID<br>起動ファイルに応じて`cmd`，`system`，`module`にいずれか記載 |
| `checks` | `controller`: 処理するPCのID<br>`cmd`：実行コマンド<br>`arg`：コマンドの引数 |

＊チェックスクリプトとは，actionsで実行した処理が正常に完了しているか確認するスクリプトである.これは True か False のみを出力する必要がある．（例：data_monitor.py）


### 4.3 `run`
起動したいモジュールを記載する．
```yaml
run:
  pc1:
    system: []
    module:
      - hsr_hri_action Move_action
      - hsr_hri_action Approach_action
```
`system`には複数起動ファイル（ROSの場合 launch，RTMの場合 rtsp），`module`には単体起動ファイル（node，rtc）を記載する．各要素は`パッケージ名 ファイル名`を半角スペースで区切って記述し，拡張子はなしとする．


### 4.4 `network`
```yaml
network:
  - id: pc1
    local: true
    host: "YOUR_IP_HERE"
    user: "YOUR_USERNAME_HERE"
    pswd: "YOUR_PASSWORD_HERE"
```

`run`や`setup`に記載するPC ID（例：`pc1`，`pc2`）を，ここで対応づける．
pc1はローカルPC（systemoperate やエンジンを実行する pc）の情報を入力する．
| 項目 | 説明 |
| --- | --- |
| `id` | 識別id．任意のidをつける |
| `local` | ローカルPCの場合は true，それ以外は false |
| `host` | IPアドレス |
| `user` | ユーザ名 |
| `pswd` | 上記ユーザ名でのパスワ−ド |


### 4.5 `ros` / `ros2`
ROSのバージョンと，ROS2の場合はdomain_idを記載する．
```yaml
ros:
  version: 2
ros2:
  domain_id: 1
```

## 5. シナリオファイル
シナリオファイルには，実行するタスクとそのパラメータを記載する．
現行のService Applicationではscenario.yamlというファイル名を前提としている．

## 6. 実行方法
### 6.1 コマンド形式

```bash
python3 Systemoperate.py <ロボット名> <シナリオ名> <操作> <マスターIP>

#例
python3 Systemoperate.py HSR scenario run 192.168.50.111
```
＊確認済みのService Application（service_app）では、シナリオ実行時に $HOME/RTSI_FW/scenario.yaml を固定で読み込む実装となっているため，第二引数で指定したシナリオがそのまま実行されるわけではない．

### 6.2 実行引数一覧

| 操作 | 主な処理 |
| --- | --- |
| `collect` | ロボット設定とシナリオから必要パッケージを収集 |
| `build` | ROS/RTMパッケージのビルドおよびWasanbon Web APIを介したビルド |
| `set` | ROS/ROS2とネットワークの設定 |
| `run` | サーバ・セットアップ・モジュール・Service Applicationの起動 |
| `setrun` | `set`+`run`の処理 |

### 6.3 内部の処理の流れ
`run`/`setrun`を実行した場合，以下の処理となる．

1. ロボット設定・シナリオの読込とROSバージョン判別
2. `common_hri_ros1`/`common_hri_ros2`のロボット別`robot.yaml`、`hri.xml`を配置
3. 必要に応じて通信設定（`setrun`）
4. Wasanbon Webサーバなどの起動確認とセットアップ実行
5. ロボット固有の`run`設定に従ってWeb APIでモジュールを起動
6. シナリオに必要なHRI機能の起動設定を生成して実行
7. Service Applicationを起動

Wasanbon Webへの要求先は，現行コードでは`http://<host>:8000/`を用いる．

## 7. 参考

- [RTSI-FW 日本語README](../README.ja.md)
- [RTSI-FW 英語README](../README.md)
- [旧版v0.8](https://github.com/rsdlab/RTSI_FW/tree/v0.8)

