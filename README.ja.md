# RT System Integration Framework（RTSI-FW）

[English](README.md) | **日本語**

## 概要
- RoIS 2.0に準拠したロボットシステム運用・管理フレームワーク
- 必要なモジュールの収集，ビルド，シナリオに基づくサービス実行を行う
- モジュールのダウンロードやシステムの起動を一括で行うSystemoperate.py，一連の実行に必要な固有情報を設定するロボットファイル，実行タスクとパラメータを設定するシナリオファイルで構成される


## バージョン
| バージョン | ブランチ | 内容 |
| --- | --- | --- |
| v1.0 | `main` | ROS2対応を追加，HRIコンポーネントを共通化，その他修正 |
| v0.8 | [`v0.8`](https://github.com/rsdlab/RTSI_FW/tree/v0.8) | 初代，ROS1・RTMに対応 |

## 開発環境
- 開発言語：Python
- OS：Ubuntu 20.04 / 22.04
- ROS：ROS 1 Noetic / ROS 2 Humble
- RTミドルウェア:OpenRTM-aist-2.0

## 再利用したフレームワーク
- [wasanbon](https://github.com/rsdlab/wasanbon/tree/ros1-ros2)
- [Wasanbon Web Framework](https://github.com/rsdlab/wasanbon_webframework/tree/main)

## 他に必要なパッケージ
| ファイル・ディレクトリ | 役割 |
| --- | --- |
|[rois_env](https://github.com/rsdlab/rois_env)|Service Applicationを有するパッケージ|
|[common_hri_ros1](https://github.com/rsdlab/common_hri/tree/main/common_hri_ros1)|ROS1で動作させる場合に使用する，HRI機能を有するパッケージ|
|[common_hri_ros2](https://github.com/rsdlab/common_hri/tree/main/common_hri_ros2)|ROS2で動作させる場合に使用する，HRI機能を有するパッケージ|

## リポジトリ内のファイル
| ファイル・ディレクトリ | 役割 |
| --- | --- |
| `Systemoperate.py` | 収集・ビルド・通信設定・起動を行うCLI |
| `ROBOT.yaml` | ロボットごとのソフトウェア・起動・通信設定 |
| `scenario.yaml` | 実行するタスクとその引数を記述するファイル |
| `process_waweb/` | Wasanbon Webの起動・停止等に関する補助スクリプト |
| `setup/` | 初期化処理の完了確認に使用するユーティリティ |

## システム構成
```text
  Systemoperate.py（システム運用管理）
          ↓
  HRIコンポーネント[common_hri_ros1 / common_hri_ros2]
          ↓
 　　実行ノード[airec_hri_action / hsr_hri_action 等]
          ↓
  実機・シミュレータ
```

## ドキュメント
マニュアル：　[English](docs/manual.md) | [日本語](docs/manual.ja.md)

