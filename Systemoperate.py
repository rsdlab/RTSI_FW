#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import yaml
import subprocess
from subprocess import *
import os
import sys
import time
import pexpect
import xml.etree.ElementTree as ET
from typing import Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor
import json
import shlex

BASH = '/bin/bash'
home_path = os.environ['HOME']
ros_ws = os.environ['ROS_WS']
rtm_ws = os.environ['RTM_WS']


############################## YAML形式のシナリオファイルの読み込み ##############################
# YAMLファイルを読み込んでPythonオブジェクトを返す
def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)


# リスト結合
# リストに要素を追加して返す簡易ヘルパー
def join_yaml(_list, item):
    _list.append(item)
    return _list

############################### スクリプトの依存関係を解析 (未使用)##############################
# スクリプトのimport依存を分類する（未使用）
def analyze_script_dependencies(script_path, special_modules=None, ros_modules=None, ros_modules_add=None):
    """
    スクリプトの依存関係を解析し、標準ライブラリ、ROS関連ライブラリ、
    外部ライブラリ（pipでインストール可能/不可）に分類する。

    Args:
        script_path (str): 解析対象のスクリプトパス
        special_modules (dict): 特別に扱いたいモジュール（例: {'module_name': 'pip_package_name'}）
        ros_modules (list): ROS関連のモジュール名リスト（desktop-fullに含まれるもの）
        ros_modules_add (list): ROS関連のモジュール名リスト（desktop-fullに含まれないもの）

    Returns:
        dict: 標準ライブラリ、ROS関連ライブラリ、pipインストール可能/不可の外部ライブラリを含む辞書
    """
    if special_modules is None:
        special_modules = {'speech_recognition': 'SpeechRecognition', 'cv2': 'opencv-python' , 'yaml' : 'PyYAML'}
    if ros_modules is None:
        ros_modules = ['ros', 'rospy', 'roslib', 'std_msgs', 'geometry_msgs', 'move_base_msgs','modules',
                       'nav_msgs', 'rosparam', 'rosnode', 'actionlib', 'sensor_msgs','tf']
    if ros_modules_add is None:
        ros_modules_add = ['moveit_commander', 'cv_bridge', 'ros_control', 'ros_arduino_bridge']

    # ROSモジュール名からAPTパッケージ名への変換辞書
    ros_module_to_package = {
        'moveit_commander': 'moveit',  # モジュールとして確認するのは 'moveit_commander' だが、パッケージ名としては 'moveit'
        'cv_bridge': 'cv-bridge',
        'ros_control': 'ros-controllers',
        'ros_arduino_bridge': 'ros_arduino_bridge'
    }

    # 標準ライブラリのパスを取得
    standard_libs_path = sysconfig.get_paths()["stdlib"]

    def is_apt_installable(module_name):
        """APTでインストール可能かどうかを確認"""
        try:
            result = subprocess.run(
                ["apt-cache", "search", module_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return bool(result.stdout.strip())  # 検索結果があればTrue
        except Exception as e:
            print(f"Error checking {module_name} in APT: {e}")
            return False

    def is_standard_lib(module_name):
        """標準ライブラリかどうかを判定"""
        try:
            module_spec = importlib.util.find_spec(module_name)
            if module_spec is None or not module_spec.origin:
                return False
            return module_spec.origin.startswith(standard_libs_path)
        except ModuleNotFoundError:
            return False

    def is_pip_installable(module_name):
        """PyPIでパッケージが存在するかを確認し、結果に基づいて変数を設定する"""
        url = f"https://pypi.org/pypi/{module_name}/json"
        response = requests.get(url)

        if module_name == "modules" or module_name == "time":
            return False

        # パッケージが存在する場合
        if response.status_code == 200:
            return True         

        else:
            return False

    # スクリプトを解析してimport文を抽出
    imported_modules = []

    with open(script_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith("import "):
                module = line.split()[1].split('.')[0]
                imported_modules.append(module)
            elif line.startswith("from "):
                module = line.split()[1].split('.')[0]
                imported_modules.append(module)

    # スクリプトにインポートされていないモジュールは除外
    imported_modules = list(set(imported_modules))

    # モジュールを分類
    standard_dependencies = []
    ros_dependencies = []
    ros_add_dependencies = []
    external_dependencies = []

    # ROSモジュールの変換処理
    ros_modules_add_translated = [ros_module_to_package.get(module, module) for module in ros_modules_add]

    for module in imported_modules:
        if module in ros_modules:
            ros_dependencies.append(module)
        elif module in ros_modules_add:  # 変換前のモジュール名を使用
            package_name = ros_module_to_package.get(module, module)
            ros_add_dependencies.append(package_name) 
        elif is_standard_lib(module):
            standard_dependencies.append(module)
        else:
            external_dependencies.append(module)

    # # ros_modules_add 内のモジュールがインポートされている場合、対応するパッケージ名を ros_add_dependencies に追加
    # for ros_module in ros_modules_add:
    #     if ros_module in imported_modules:  # モジュールがインポートされている場合のみ追加
    #         package_name = ros_module_to_package.get(ros_module, ros_module)
    #         # もし ros_add_dependencies にすでにそのパッケージ名が含まれていなければ追加
    #         if package_name not in ros_add_dependencies:
    #             ros_add_dependencies.append(package_name)


    # 外部ライブラリをpipインストール可能か判定
    pip_installable = []
    apt_installable = []
    not_pip_installable = []

    # 特別扱いのモジュール（speech_recognition, cv2など）は事前にリストに追加
    for original_module, pip_name in special_modules.items():
        if original_module in imported_modules:  # インポートされている場合のみ処理
            if is_pip_installable(pip_name):
                pip_installable.append(pip_name)  # pip_name（例えば、SpeechRecognitionやopencv-python）を追加
            else:
                not_pip_installable.append(original_module)

    # その他の外部ライブラリをチェック
    for module in external_dependencies:
        if module not in special_modules and module in imported_modules:  # 特別に扱いたいモジュールはスキップ
            if is_pip_installable(module):
                if module == "openai":
                    pip_installable.append("openai==0.27.8")
                else:
                    pip_installable.append(module)
            elif is_apt_installable(module):
                apt_installable.append(module)
            else:
                not_pip_installable.append(module)


    return {
        "standard_libraries": standard_dependencies,
        "ros_libraries": ros_dependencies,
        "ros_additional_libraries": ros_add_dependencies,  # ここで結果に変換された名前を含める
        "pip_installable": pip_installable,
        "apt_installable": apt_installable,
        "not_pip_installable": not_pip_installable,
    }


############################### スクリプトの依存関係を追加 (未使用)##############################
# 依存情報を既存YAMLにマージして保存
def update_yaml_with_dependencies(yaml_path1, dependencies , yaml_path2):
    """ 既存のYAMLに新しい依存関係を追加 """
    existing_data = load_yaml(yaml_path1) if os.path.exists(yaml_path1) else {}

    # 既存のYAMLファイルを読み込む
    if os.path.exists(yaml_path1):
        with open(yaml_path1, 'r') as yaml_file:
            existing_data = yaml.safe_load(yaml_file) or {}
    else:
        existing_data = {}

    # 既存データを保持したまま、'collect'セクションに新しいデータを追加
    if "collect" in existing_data:
        existing_data["collect"]["rtm"].extend(dependencies["collect"]["rtm"])
        existing_data["collect"]["apt"].extend(dependencies["collect"]["apt"])
        existing_data["collect"]["pip"].extend(dependencies["collect"]["pip"])
        existing_data["collect"]["git"].extend(dependencies["collect"]["git"])
        existing_data["collect"]["other"].extend(dependencies["collect"]["other"])
    else:
        existing_data["collect"] = dependencies["collect"]

    # 既存データをYAML形式で書き込み
    with open(yaml_path2, 'w') as yaml_file:
        yaml.dump(existing_data, yaml_file, sort_keys=False,default_flow_style=False, allow_unicode=True)

    # print(f"依存関係が {yaml_path2} に保存されました。")

    return yaml_path2


# Noneを除外してデータを整形
def filter_empty_items(items):
    """ 空の値を除外するヘルパー関数 """
    if isinstance(items, list):
        # Noneのみを除外
        return [item for item in items if item is not None]
    elif isinstance(items, dict):
        # Noneのキーや値を削除
        return {k: v for k, v in items.items() if v is not None}
    return items


# ○yamlファイル読み込み
# YAMLファイルを読み込むヘルパー（collect/run用）
def load_yaml(file):
    """ YAMLファイルを読み込むヘルパー関数（仮定） """
    with open(file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


# ○collect用のyamlを合成する関数
# collect用YAMLを統合して新規保存
def combined_collectfile(files):
    """ 複数のYAMLファイルを統合する（collect用） """

    combined_file = 'combined_collect.yaml'
    combined_data = {'collect': {key: [] for key in ["rtm", "apt", "pip", "git", "other"]}}

    for file in files:
        data = load_yaml(file)
        for key in ["rtm", "apt", "pip", "other"]:
            combined_data['collect'][key] = list(set(combined_data['collect'][key] + data.get('collect', {}).get(key, [])))
        combined_data['collect']['git'].extend(repo for repo in data.get('collect', {}).get('git', []) if repo.get('url'))

    # 結果を新しいYAMLファイルに保存
    with open(combined_file, 'w', encoding='utf-8') as output_file:
        yaml.dump(combined_data, output_file, allow_unicode=True, sort_keys=False)

    print("統合が完了しました！")

    return combined_file


# ○run用のyamlを合成する関数
# run用YAMLを統合して新規保存
def combined_runfile(files):
    combined_file = 'Launch.yaml'

    """ 複数のYAMLファイルを統合する（run用） """
    combined_data = {'run': {key: [] for key in ["rtm", "rosrun", "roslaunch"]}}

    for file in files:
        data = load_yaml(file)
        for key in ["rtm", "rosrun", "roslaunch"]:
            combined_data['run'][key] = list(set(combined_data['run'][key] + data.get('run', {}).get(key, [])))

    with open(combined_file, 'w', encoding='utf-8') as output_file:
        yaml.dump(combined_data, output_file, allow_unicode=True, sort_keys=False)

    return combined_file

# 新しい形式のrunセクションを持つYAMLを生成する関数
# system/module形式のrun YAMLを生成
def create_new_run_yaml(system_commands, module_commands):
    """
    新しい形式（system/module）のrunセクションを持つYAMLファイルを生成する。
    """
    output_file = "Launch.yaml"  # 出力ファイル名
    data = {
        'run': {
            'system': system_commands,
            'module': module_commands,
        }
    }

    with open(output_file, 'w', encoding='utf-8') as outfile:
        yaml.dump(data, outfile, sort_keys=False, default_flow_style=False, allow_unicode=True)

    return output_file

# # ○hri-c用のlaunchのyamlを作成する
# def update_yaml_launch_file(launch_files):
    
#     script_path = os.path.join(home_path, rtsi_dir) #ディレクトリ名
#     os.chdir(script_path)

#     # 現在のディレクトリを表示
#     subprocess.run(["pwd"])

#     # 依存部分？
#     output_file = "seed_hri.yaml"
#     keys_to_replace = ['rtm','roslaunch', 'rosrun']
#     route_key = 'run'

#     output_file = item_replace_null(output_file, route_key, keys_to_replace)
    
#     with open(output_file , 'r') as infile:
#         data = yaml.safe_load(infile)

#     # nullを削除して空リストに変換（既存データから）(必要？)
#     data['run']['rtm'] = [item for item in data['run']['rtm'] if item is not None]
#     data['run']['roslaunch'] = [item for item in data['run']['roslaunch'] if item is not None]
#     data['run']['rosrun'] = [item for item in data['run']['rosrun'] if item is not None]

#     # スクリプトを条件に基づいて追加
#     for script in launch_files:
#         if '.launch' in script:
#             if script not in data['run']['roslaunch']:  # 重複防止（必要？）
#                 data['run']['roslaunch'].append(script)
#         else:
#             if script not in data['run']['rosrun']:  # 重複防止（必要？）
#                 data['run']['rosrun'].append(script)


#     # `run` セクションを新しいファイルに書き込む
#     with open(output_file, 'w') as outfile:
#         yaml.dump(data, outfile, sort_keys=False, default_flow_style=False)

#     print(f"'run' section has been written to {output_file}")
    
#     return output_file

# ○分析のメイン処理(collect)
# collect対象のYAMLパスを組み立てて統合
def analyze(engine,functions):

    collect_list = []

    for launch_file in functions:    
        print(f"HRI機能: {launch_file}")

    if engine == "None":
        return None

    files_list = [os.path.join(home_path, "catkin_ws", "src", engine, "yaml", f"{file}.yaml") for file in functions]

    return combined_collectfile(files_list)



################################ 分析のメイン処理(run) ###############################
# ○
# run用のsystem/moduleコマンドを生成してYAML化
def analyze2(engine_name, robot_path, functions):  
    # 新しい形式のコマンドリストを初期化
    system_commands = []
    module_commands = []

    # hri_script = [] # 使わなくなった

    print(f"使用するHRI-Component {functions}")

    if functions[0] == None:
        print("pass")
    else:
        # エンジンファイルの起動
        engine_command = get_enginefile(engine_name)
        if engine_command != "None":
            package_name, command_name = engine_command.split(maxsplit=1)
            module_commands.append(f"{package_name} {command_name.replace('.py', '')}")

        # タスクファイルの起動
        for launch_file in functions:
            module_command = engine_name + ' ' + launch_file
            package_name, command_name = module_command.split(maxsplit=1)
            module_commands.append(f"{package_name} {command_name}")

    # 新しい形式のYAMLファイルを生成
    output_yaml_file = create_new_run_yaml(system_commands, module_commands)
    print(f"Generated new format YAML: {output_yaml_file}")  # デバッグ用

    # 古い形式の処理を削除（combined_runfile, update_yaml_launch_file など）
    # 新しい形式ではLaunch.yamlを直接生成するため、これらの関数は不要

    return output_yaml_file



############################### Engineのノード名を取得する ###############################
# ○
# engineのhri.xmlから起動ファイル名を取得
def get_enginefile(engine_name):
    print(engine_name)
    directory = ros_ws + "/src/" + engine_name + "/hri.xml"
    # XMLファイルをパース
    tree = ET.parse(directory)
    root = tree.getroot()
    # 名前空間を定義
    namespaces = {
        'gml': 'http://example.com/r/gml',
        'rois': 'http://example.com/r/rois'
    }

    filename = root.find('gml:filename', namespaces)
    if filename is not None:
        filename_text = filename.text # '.py' を削除
        engine = engine_name +' ' + filename_text
        return engine
    else:
        return "None"
    

# collectセクションに従い依存パッケージを取得
def collect(yml_path):
    # with open(args[1] , 'r') as yml:
    #     config = yaml.safe_load(yml)

    if  yml_path == None:
        return
    with open(yml_path , 'r') as yml:
        config = yaml.safe_load(yml)
    

 ######### wasanbon repository #####################    
    os.chdir(rtm_ws)
    # subprocess.run("pwd")
    rtm_item = config.get('collect', {}).get('rtm', [])
    leng_rtm = [item for item in rtm_item if item is not None]
    length_rtm = len(leng_rtm)
    print(f"wasanbonパッケージの個数: {length_rtm}")


    if length_rtm == 0:
        print("rtm pass")
        pass
    else:
        print("install wasanbon repository")
        for i in range(length_rtm):
            was_rep1 = config['collect']['rtm'][i]
            print(was_rep1)
            ser_rtm = './{}'.format(was_rep1)
            if os.path.isdir(ser_rtm):
                print("rtm File exit already")
            else:
                was_rep11 = 'wasanbon-admin.py repository clone {} -v' .format(was_rep1)
                print(was_rep11)
                call(was_rep11.split())

 ######### engine repository #####################    
    path_ros = ros_ws + "/src/"
    os.chdir(path_ros)
    engine_item = config.get('collect', {}).get('engine', [])
    leng_engine = [item for item in engine_item if item is not None]
    length_engine = len(leng_engine)
    print(f"hri engineパッケージの個数: {length_engine}")


    if length_engine == 0:
        print("engine pass")
        pass
    else:
        print("install engine repository")
        for i in range(length_engine):
            was_rep1 = config['collect']['engine'][i]
            print(was_rep1)
            ser_engine = './{}'.format(was_rep1)
            if os.path.isdir(ser_engine):
                print("engine File exit already")
            else:
                was_rep11 = 'wasanbon-admin.py repository clone {} -v' .format(was_rep1)
                print(was_rep11)
                call(was_rep11.split())

 ######### apt repository #####################

    apt_item = config.get('collect', {}).get('apt', [])
    leng_apt = [item for item in apt_item if item is not None]
    length_apt = len(leng_apt)
    print(f"aptの個数: {length_apt}")

    if length_apt == 0:
        print("apt pass")
        pass
    else:

        for i in range(length_apt):
            ccc = config['collect']['apt'][i]
            print(ccc)
            install = "sudo -S apt -y install  {}".format(ccc)
            password = "rsdlab\n".encode()
            subprocess.run(install.split(), input=password)



 ######### pip repository #####################

    pip_item = config.get('collect', {}).get('pip', [])
    leng_pip = [item for item in pip_item if item is not None]
    length_pip = len(leng_pip)
    print(f"pipの個数: {length_pip}")

    if length_pip == 0:
        print("pip pass")
        pass
    else:

        for i in range(length_pip):
            ccc = config['collect']['pip'][i]
            print(ccc)

            subprocess.run([ 'pip', 'install', str(ccc)])

 ######### ros package #####################
    # subprocess.run("pwd")#workspace
    dir_name = f"{ros_ws}/src" 
    os.chdir(dir_name)
    # os.chdir(os.environ['HOME'])
    # os.chdir('catkin_ws/src')

    git_items = config.get('collect', {}).get('git', [])
    repo_count = sum(1 for item in git_items if isinstance(item, dict) and 'url' in item and item['url'])

    print(f"repoの個数: {repo_count}")

    if repo_count == 0:
        print("git pass")
        pass

    else:

        for i in range(repo_count):
            url = config['collect']['git'][i]['url']
            repo = config['collect']['git'][i]['repo']
            print(f"repository{i} name :{repo}")
            branch = config['collect']['git'][i]['branch']
            if branch == None:
                pass

            ser_git = f'{ros_ws}/src/'+ str(repo)
            # print(f"repository path :{ser_git}")
            if os.path.isdir(ser_git):
                print("repository exit already")
            else:
                if branch == None:
                    print('clone repository' )
                    subprocess.run(['git', 'clone', str(url)])
                else:
                    print('clone repository '+ str(branch))
                    subprocess.run(['git', 'clone', '-b', str(branch) ,str(url)])
                    time.sleep(15)

    ####################  Add  edit  modules(by editor) #####################
    if length_rtm == 0:
        print("rtm pass")
        pass
    else:
        dec_b = config['collect']['rtm'][0]
        if (dec_b == 'Destination_gui'):  #wasanbonリポジトリがDestination_guiなら
            print("move system file")     #ナビゲーション用のファイルを入れる
            move_file()
        else:
            print("move file for navigation")
    
 ######### add package ######################
        dec = config['collect']['rtm'][0]

        if (dec == 'MobileRobotControl'):  #wasanbonリポジトリがMobileRobotControlなら
            print("install sfml")          #SFMLライブラリを入れる
            sfml()
        else:
            print("not install sfml")


# serializerファイルをbinへコピー
def serializer(RTC,FILE):
    print("move dir to so")
    os.chdir('bin')

    subprocess.run("pwd")
    subprocess.run(['ls'])
        
    ser = './{}'.format(FILE)
    if os.path.isfile(ser):
        print("File exit already")
    else:
        ser_copy = '../rtc/{0}/build-linux/serializer/{1}'.format(RTC,FILE)
        shutil.copy(ser_copy,ser)


# ROS/RTMパッケージのビルドを実行
def _build(yml_path,service):
    with open(yml_path , 'r') as yml:
        config = yaml.safe_load(yml)

 ######### Build  ros package #####################
    print("Build ROS package")
    print("catkin build")
    os.chdir(ros_ws)
    
    subprocess.run(["rosdep", "install", "-y", "-r", "--from-paths", "src", "--ignore-src"])
    subprocess.call(["catkin", "build",f"{service}"]) 
    print("source devel/setup.bash")
    subprocess.call("source ~/catkin_ws/devel/setup.bash",shell=True,executable = BASH) 
    # subprocess.run("pwd")

 ######### Build rtm package #####################
    leng_rtm = config['collect']['rtm']
    length_rtm = len(leng_rtm)
    for i in range(length_rtm):
        was_rep1 = config['collect']['rtm'][i]
        dir_name = f"{rtm_ws}/{was_rep1}" 
        os.chdir(dir_name)
        # os.chdir(os.environ['HOME'])
        # os.chdir('workspace/{}'.format(was_rep1))
        # subprocess.run("pwd")
        print('Package build {}'.format(was_rep1))
        call(['./mgr.py', 'rtc', 'build', 'all','-v'])

def _extract_first_package(entry_list):
    if not entry_list:
        return None
    if isinstance(entry_list, list) and entry_list:
        first = entry_list[0]
    else:
        first = entry_list
    if not first or not isinstance(first, str):
        return None
    return first.split(maxsplit=1)[0]


def build(robot_path, service=None, network_info=None):
    print("build")

    if not robot_path:
        print("robot_path is empty. skip build.")
        return

    with open(robot_path, 'r') as yml:
        config = yaml.safe_load(yml) or {}

    packages_to_build = []
    ip_by_package = {}

    # collect.engine -> localhost
    engines = (config.get('collect') or {}).get('engine') or []
    for engine in engines:
        if not engine or engine == 'null':
            continue
        packages_to_build.append(engine)
        ip_by_package[engine] = 'localhost'

    # setup.package -> default localhost (controllerがあればnetworkから解決)
    network_map = _build_network_map(config)
    setup_entries = config.get('setup') or []
    for step in setup_entries:
        if not isinstance(step, dict):
            continue
        pkg = step.get('package')
        if not pkg:
            continue
        packages_to_build.append(pkg)
        controller = None
        actions_cfg = _normalize_kv_block(step.get('actions'))
        checks_cfg = _normalize_kv_block(step.get('checks'))
        controller = actions_cfg.get('controller') or checks_cfg.get('controller')
        ip_by_package[pkg] = _resolve_ip_from_controller(controller, network_map)

    # run.system/module -> first item per robot id
    run_section = config.get('run') or {}
    if isinstance(run_section, dict):
        for robot_id, group_settings in run_section.items():
            if not isinstance(group_settings, dict):
                continue
            ip = _resolve_ip_from_controller(robot_id, network_map)

            sys_pkg = _extract_first_package(group_settings.get('system') or [])
            if sys_pkg:
                packages_to_build.append(sys_pkg)
                ip_by_package.setdefault(sys_pkg, ip)

            mod_pkg = _extract_first_package(group_settings.get('module') or [])
            if mod_pkg:
                packages_to_build.append(mod_pkg)
                ip_by_package.setdefault(mod_pkg, ip)

    # 重複排除しつつ順序維持
    seen = set()
    ordered_pkgs = []
    for pkg in packages_to_build:
        if pkg in seen:
            continue
        seen.add(pkg)
        ordered_pkgs.append(pkg)

    if not ordered_pkgs:
        print("No packages to build.")
        return

    for pkg in ordered_pkgs:
        ip = ip_by_package.get(pkg, 'localhost')
        url = f"http://{ip}:8000/dev/packages/{pkg}/build"
        curl_cmd = ["curl", "-X", "POST", "-u", "admin:admin", url]
        print(f"build: {pkg} @ {ip}")
        subprocess.run(curl_cmd, check=False)
        

######### Start name server ##################### 
# roscore/rtm nameserverの起動確認と起動
def nameserver():
    # ps aux | grep rosmaster | grep -v grep の出力行数を取得
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    
    # psコマンドの結果をフィルタリングして "rosmaster" を含む行を検索
    matching_lines = [line for line in result.stdout.splitlines() if "rosmaster" in line and "grep" not in line]
    
    # "rosmaster" に関連する行があれば、それが起動しているということ
    if not len(matching_lines) > 0:
        print("roscoreが起動していません。roscoreを起動します...")
        call(["gnome-terminal", "--", "roscore"])

        # roscore起動まで待機
        time.sleep(0.5)

    else:
        print("roscoreはすでに起動しています．")

    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    
    # psコマンドの結果をフィルタリングして "omni" を含む行を検索
    matching_lines = [line for line in result.stdout.splitlines() if "omni" in line and "grep" not in line]
    print(len(matching_lines))

    if not len(matching_lines) > 0:
        print("nameserverが起動していません。namaserverを起動します...")

        # ターミナルの言語取得
        result = subprocess.run(["locale"], capture_output=True, text=True)
        matching_lines = [line for line in result.stdout.splitlines() if "en" in line]

        username = os.environ['USER']
        child = pexpect.spawn("wasanbon-admin.py nameserver start", encoding='utf-8')

        # 日本語の場合
        if not len(matching_lines) > 0:
            child.expect(f"{username} のパスワード:")

        # 英語の場合
        else:
            child.expect(f"password for {username}:")

        child.sendline(username)
        child.interact()

    else:
        print("nameserverはすでに起動しています．")


# ○
# Launch.yamlのsystem/moduleコマンドを起動
def run(yml_path = None):
    processes = {}

    print(yml_path)

    if yml_path is None:
        with open(args[1] , 'r') as yml:
            config = yaml.safe_load(yml)
    else:
        with open(yml_path , 'r') as yml:
            config = yaml.safe_load(yml)
    
    print(config)

    # system コマンドの実行
    print("Executing system commands from YAML")
    if 'system' in config.get('run', {}):
        system_commands = config['run']['system']
        if system_commands:
            for index, command_str in enumerate(system_commands):
                try:
                    package_name, command_name = command_str.split(maxsplit=1)
                    # パッケージのディレクトリを取得
                    get_dir_cmd = ["wasanbon-admin.py", "package", "directory", package_name]
                    dir_proc = subprocess.Popen(get_dir_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    stdout, stderr = dir_proc.communicate()
                    if dir_proc.returncode != 0:
                        print(f"Error getting directory for package {package_name}: {stderr}")
                        continue
                    package_dir = stdout.strip()
                    
                    # コマンド実行
                    exec_cmd = (
                        f"cd {package_dir} && ./mgr.py system run {command_name}"
                    )
                    proc = subprocess.Popen(["gnome-terminal", "--tab", "--", "bash", "-i", "-c", exec_cmd])
                    processes[f"system_{index}"] = proc.pid
                except ValueError:
                    print(f"Skipping invalid system command format: {command_str}")
                except OSError as e:
                    print(f"Failed to start system process for {command_str}: {e}")
                    continue
        else:
            print("No system commands to execute.")
    else:
        print("No 'system' section in run configuration.")

    # module コマンドの実行
    print("Executing module commands from YAML")
    if 'module' in config.get('run', {}):
        module_commands = config['run']['module']
        if module_commands:
            for index, command_str in enumerate(module_commands):
                try:
                    package_name, command_name = command_str.split(maxsplit=1)
                    # パッケージのディレクトリを取得
                    get_dir_cmd = ["wasanbon-admin.py", "package", "directory", package_name]
                    dir_proc = subprocess.Popen(get_dir_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    stdout, stderr = dir_proc.communicate()
                    if dir_proc.returncode != 0:
                        print(f"Error getting directory for package {package_name}: {stderr}")
                        continue
                    package_dir = stdout.strip()

                    # コマンド実行
                    exec_cmd = (
                        f"cd {package_dir} && ./mgr.py module run {command_name}"
                    )
                    proc = subprocess.Popen(["gnome-terminal", "--tab", "--", "bash", "-i", "-c", exec_cmd])
                    processes[f"module_{index}"] = proc.pid
                except ValueError:
                    print(f"Skipping invalid module command format: {command_str}")
                except OSError as e:
                    print(f"Failed to start module process for {command_str}: {e}")
                    continue
        else:
            print("No module commands to execute.")
    else:
        print("No 'module' section in run configuration.")
    
import yaml
import subprocess

# Wasanbon-Web経由でsystem/moduleを起動
def run_web(yml_path=None):
    processes = {}

    print(f"YAML path: {yml_path}")

    # YAMLの読み込み
    if yml_path is None:
        raise ValueError("YAML path must be provided.")
    with open(yml_path, 'r') as yml:
        config = yaml.safe_load(yml) or {}

    print("Loaded config:", config)

    run_config = config.get('run') or {}
    network_entries = config.get('network') or []

    if not run_config:
        print("No 'run' section in YAML. Nothing to execute.")
        return processes

    # ネットワーク情報を参照しやすい形へ整形
    network_map = {}
    for entry in network_entries:
        if not isinstance(entry, dict):
            continue
        robot_id = entry.get('id')
        if robot_id:
            network_map[robot_id] = entry

    def resolve_ip(robot_id: Optional[str]) -> str:
        if not robot_id:
            return 'localhost'
        network_info = network_map.get(robot_id, {})
        host = network_info.get('host') or network_info.get('ip')
        if host:
            return host
        # "local" キーがある場合は localhost を優先する
        local_flag = network_info.get('local')
        if isinstance(local_flag, str):
            local_flag = local_flag.strip().lower() in ('yes', 'true', '1')
        if local_flag:
            return 'localhost'
        return 'localhost'

    # system/module コマンドの共通実行処理
    def execute_commands(ip_address: str, commands, command_type: str, group_name: str):
        if not commands:
            print(f"No {command_type} commands to execute for {group_name}.")
            return

        for index, command_str in enumerate(commands):
            try:
                package_name, command_name = command_str.split(maxsplit=1)
            except ValueError:
                print(f"Skipping invalid {command_type} command format: {command_str}")
                continue

            url = f"http://{ip_address}:8000/dev/packages/{package_name}/{command_type}/run/{command_name}"
            curl_cmd = ["curl", "-X", "POST", "-u", "admin:admin", url]
            terminal_cmd = [
                "gnome-terminal",
                "--tab",
                "--",
                "bash",
                "-c",
                f"{' '.join(curl_cmd)}; exec bash"
            ]
            print(f"Running {command_type} command in terminal ({group_name}): {' '.join(terminal_cmd)}")
            try:
                proc = subprocess.Popen(terminal_cmd)
            except OSError as e:
                print(f"Failed to start {command_type} process for {command_str}: {e}")
                continue

            key = f"{command_type}_{group_name}_{index}"
            processes[key] = proc.pid

    if not isinstance(run_config, dict):
        print("Unexpected 'run' configuration format (expected mapping of robot IDs). Nothing executed.")
        return processes

    for robot_id, group_settings in run_config.items():
        if not isinstance(group_settings, dict):
            print(f"Skipping run configuration for {robot_id}: invalid structure {group_settings!r}")
            continue

        ip_address = resolve_ip(robot_id)
        print(f"Target IP for {robot_id}: {ip_address}")

        system_commands = group_settings.get('system', [])
        module_commands = group_settings.get('module', [])

        execute_commands(ip_address, system_commands, 'system', robot_id)
        execute_commands(ip_address, module_commands, 'module', robot_id)

    return processes


# network配列をidキーの辞書に変換
def _build_network_map(config: dict) -> Dict[str, dict]:
    network_entries = config.get('network') or []
    network_map: Dict[str, dict] = {}
    for entry in network_entries:
        if isinstance(entry, dict):
            robot_id = entry.get('id')
            if robot_id:
                network_map[robot_id] = entry
    return network_map


# controller IDからIP/hostを解決
def _resolve_ip_from_controller(controller_id: Optional[str], network_map: Dict[str, dict]) -> str:
    """controller(id) から host/ip を解決。見つからない場合は localhost を返す"""
    if not controller_id:
        return 'localhost'

    entry = network_map.get(controller_id, {})
    host = entry.get('host') or entry.get('ip')
    if host:
        return host

    local_flag = entry.get('local')
    if isinstance(local_flag, str):
        local_flag = local_flag.strip().lower() in ('yes', 'true', '1')
    if local_flag:
        return 'localhost'

    return 'localhost'


# actions/checksブロックを辞書に正規化
def _normalize_kv_block(block) -> Dict[str, str]:
    if not block:
        return {}
    if isinstance(block, dict):
        return {k: v for k, v in block.items() if v not in (None, '')}

    normalized: Dict[str, str] = {}
    if isinstance(block, list):
        for entry in block:
            if not isinstance(entry, dict):
                continue
            for k, v in entry.items():
                if v not in (None, ''):
                    normalized[k] = v
    return normalized


# curl出力末尾のJSON行を抽出
def _parse_json_line(raw_output: str) -> Optional[dict]:
    for line in reversed(raw_output.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


# 対象パッケージのミドルウェア種別を取得
def _check_middleware_type(package_name: str, controller_id: Optional[str], network_map: Dict[str, dict]) -> Optional[str]:
    if not package_name:
        return None

    ip_address = _resolve_ip_from_controller(controller_id, network_map)
    # print(ip_address,package_name)
    url = f"http://{ip_address}:8000/dev/packages/{package_name}/check/middleware"
    curl_cmd = ["curl", "-X", "GET", "-u", "admin:admin", url]
    try:
        result = subprocess.run(curl_cmd, capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        print(f"middleware check timeout ({package_name}@{controller_id})")
        return None

    if result.returncode != 0:
        print(f"middleware check failed ({package_name}@{controller_id}): {result.stderr.strip()}")
        return None

    payload = _parse_json_line(result.stdout)
    middleware_type = None
    if isinstance(payload, dict):
        middleware_type = payload.get("middleware") or payload.get("type")
    if middleware_type is None:
        middleware_type = result.stdout.strip()

    output_text = middleware_type
    if controller_id:
        print(f"middleware({controller_id}): {output_text}")
    else:
        print(f"middleware: {output_text}")

    return middleware_type or result.stdout.strip() or None


# package/command文字列を分割
def _parse_package_command(command_str: str) -> Tuple[str, str]:
    parts = command_str.split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


# setup actionsを順に実行
def _execute_setup_actions(actions_cfg: Dict[str, str], network_map: Dict[str, dict]):
    if not actions_cfg:
        print("No setup actions to execute.")
        return

    controller_id = actions_cfg.get('controller')
    controller_ip = _resolve_ip_from_controller(controller_id, network_map)

    # ローカルコマンド
    action_cmd = actions_cfg.get('cmd')
    if action_cmd:
        cmd_parts = shlex.split(action_cmd)
        print(f"Executing setup cmd locally: {' '.join(cmd_parts)}")
        cmd_line = f"source ~/.bashrc; {action_cmd}"
        subprocess.run([BASH, "-ic", cmd_line], check=False)

    # system / module コマンド
    for cmd_type in ("system", "module"):
        command_entry = actions_cfg.get(cmd_type)
        if not command_entry:
            continue

        package_name, command_name = _parse_package_command(command_entry)
        if not command_name:
            print(f"Skipping {cmd_type} action with invalid format: {command_entry}")
            continue

        url = f"http://{controller_ip}:8000/dev/packages/{package_name}/{cmd_type}/run/{command_name}"
        curl_cmd = ["curl", "-s", "-X", "POST", "-u", "admin:admin", url]
        print(f"Executing setup {cmd_type} via {controller_ip}: {url}")
        result = subprocess.run(curl_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"{cmd_type} action failed for {command_entry}: {result.stderr.strip()}")
        elif result.stdout.strip():
            print(result.stdout.strip())


# setup checksを実行して合否判定
def _perform_setup_checks(checks_cfg: Dict[str, str], middleware_type: Optional[str] = None) -> bool:
    if not checks_cfg:
        print("No setup checks to execute.")
        return True

    check_cmd = checks_cfg.get('cmd')
    if not check_cmd:
        print("Check command is empty; skipping checks.")
        return True

    cmd_parts = shlex.split(check_cmd)
    arg_list = []
    if middleware_type:
        # 取得結果が \"ros\" のようにクォートされていても素の文字列にする
        cleaned = middleware_type
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
            cleaned = cleaned[1:-1]
        arg_list.append(cleaned)
    arg = checks_cfg.get('arg')
    if arg:
        if isinstance(arg, list):
            arg_list.extend([str(a) for a in arg if a is not None])
        else:
            arg_str = str(arg)
            if ',' in arg_str:
                arg_list.extend([p.strip() for p in arg_str.split(',') if p.strip()])
            else:
                arg_list.append(arg_str)
    cmd_parts.extend(arg_list)

    for attempt in range(2):
        print(f"Running check attempt {attempt + 1}: {' '.join(cmd_parts)}")
        cmd_line = f"source ~/.bashrc; {' '.join(cmd_parts)}"
        result = subprocess.run([BASH, "-ic", cmd_line], capture_output=True, text=True)
        output = (result.stdout or '').strip().lower()
        if output == 'true':
            print("Check passed.")
            return True
        print(f"Check attempt {attempt + 1} result: {output or result.stderr.strip()}")

    print("error")
    return False


# setupセクションを順次実行
def process_setup(yml_path: str) -> bool:
    """setup セクションを順番に実行し、checks が通れば次へ進む"""
    if not yml_path:
        return True

    with open(yml_path, 'r') as yml:
        config = yaml.safe_load(yml) or {}

    setup_entries = config.get('setup') or []
    if not setup_entries:
        print("No setup section found; skipping setup.")
        return True

    network_map = _build_network_map(config)

    for step in setup_entries:
        name = step.get('name') or 'setup'
        package_name = step.get('package')
        actions_cfg = _normalize_kv_block(step.get('actions'))
        checks_cfg = _normalize_kv_block(step.get('checks'))

        print(f"--- setup: {name} ---")

        controller_hint = actions_cfg.get('controller') or checks_cfg.get('controller')
        middleware_type = _check_middleware_type(package_name, controller_hint, network_map)

        _execute_setup_actions(actions_cfg, network_map)
        if not _perform_setup_checks(checks_cfg, middleware_type):
            print(f"Setup step '{name}' failed.")
            return False

    print("All setup steps completed.")
    return True



# ○YAMLからシナリオを読み込みサービス名とタスクを抽出する
# シナリオから機能名リストを抽出
def scenario_analyze(scenario_path):
   
    os.chdir(system_dir)

    scenario_data = load_yaml(scenario_path)
    scenario = scenario_data.get('scenario', [])

    tasks = []
    functions = []

    # print(service)

    # シナリオに基づいて機能名と引数を抽出
    for task in scenario:
        task_name = task.get('task', '')
        task_arg = task.get('arg', '')

        # 機能と引数をリストに追加
        tasks.append((task_name, task_arg))
        # print(tasks)

        if task_name not in functions:
            functions.append(task_name)
        else:
            pass

    return functions


# 全ノード停止とRTC停止を実行
def stop_all_processes():
    subprocess.call(["rosnode", "kill", "-a"])
    deactivate_remote_rtcs(args[4])
    subprocess.run(['rosnode', 'cleanup'], input='y\n'.encode('utf-8'), check=False)

# 指定IP上のRTCを検索してDeactivate
def deactivate_remote_rtcs(target_ip):
    print(f"--- Searching for RTCs on {target_ip} ---")
    
    #rtfind コマンドを実行してリストを取得
    try:
        result = subprocess.run(
            ["rtfind", f"{target_ip}/"], 
            capture_output=True, 
            text=True, 
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error: rtfind command failed. {e}")
        return

    found_paths = result.stdout.splitlines()

    #見つかったパスの中から .rtc で終わるものだけを抽出して rtdeact
    count = 0
    for path in found_paths:
        path = path.strip()
        
        if path.endswith(".rtc"):
            print(f"Deactivating: {path}")
            
            try:
                subprocess.run(["rtdeact", path], check=False)
                count += 1
            except Exception as e:
                print(f"Failed to deactivate {path}: {e}")

    if count == 0:
        print("No active RTCs found to deactivate.")
    else:
        print(f"--- Finished. Deactivation attempted for {count} components. ---")
    
# robot YAMLからネットワーク情報を構造化
def get_network_info(master_ip, robot_path):
    config_data = load_yaml(robot_path)
    network_info = config_data.get('network', [])

    local_ip = None
    if network_info:
        local_ip = network_info[0].get('host')

    managed_ips = []
    managed_users = []
    managed_pswds = []

    for pc in network_info:
        if not pc.get('local'):
            managed_ips.append(pc.get('host'))
            managed_users.append(pc.get('user'))
            managed_pswds.append(pc.get('pswd'))

    network_config = {
        "master": master_ip,
        "local": local_ip,
        "managed": managed_ips,
        "managed_user": managed_users,
        "managed_pswd": managed_pswds
    }

    return network_config

# ネットワーク設定を一括適用
def set_network(network_info, robot_path):
    print("set_start")

    # master_ipのbash確認
    ip_state=check_master(network_info)
    
    #設定済みだったら、
    if ip_state==True:
        print("state true")
        # 設定
        set_server(network_info, robot_path)

   
    #設定済みじゃなかったら
    else:
        print("state false")
        
        # rosのみ変更
        set_ros(network_info)

        # パッケージごとに変更
        set_server(network_info, robot_path)


# master設定の有効性をリモートチェック
def check_master(network_info):
    print("check master")
    if not network_info:
        print("network_infoが指定されていません。")
        return False

    master_ip = network_info.get("master")
    if not master_ip:
        raise ValueError("network_info に 'master' が含まれていません。")

    managed_hosts = network_info.get("managed") or []
    # if not managed_hosts:
    #     print("managed ホストが設定されていないためチェックは実施しません。")
    #     return True

    local_ip = network_info.get("local")
    targets = []
    if local_ip:
        targets.append(local_ip)
    targets.extend(managed_hosts)
    print(targets)

    def parse_is_ok(raw_output: str) -> bool:
        lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "is_ok" in payload:
                return bool(payload["is_ok"])
        print(f"予期しない応答: {raw_output}")
        return False

    def run_check(host: str) -> bool:
        if not host:
            print("IP アドレスが空の項目があります。")
            return False
        curl_cmd = (
            f"curl -X GET -u admin:admin "
            f"http://{host}:8000/server/check/{master_ip}"
        )
        proc = subprocess.run(
            ["bash", "-lc", curl_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"{host} へのチェックに失敗しました: {proc.stderr.strip()}")
            return False
        return parse_is_ok(proc.stdout)

    results = [run_check(host) for host in targets]
    return all(results)

# ROS master設定を各ホストへ適用
def set_ros(network_info):
    print("set_ros")
    if not network_info:
        raise ValueError("network_info が指定されていません。")

    master_ip = network_info.get("master")
    if not master_ip:
        raise ValueError("network_info に 'master' が含まれていません。")

    targets = []
    local_ip = network_info.get("local")
    if local_ip:
        targets.append(local_ip)

    managed_hosts = network_info.get("managed") or []
    for host in managed_hosts:
        if host:
            targets.append(host)

    if not targets:
        print("set_ros: 対象ホストが見つかりませんでした。")
        return False

    def parse_is_ok(raw_output: str) -> bool:
        lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "is_ok" in payload:
                return bool(payload["is_ok"])
        return False

    def run_set(host: str) -> bool:
        curl_cmd = (
            f"curl -X PUT -u admin:admin "
            f"http://{host}:8000/set/ros/{master_ip}"
        )
        proc = subprocess.run(
            ["bash", "-lc", curl_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"{host} で set_ros 実行に失敗しました: {proc.stderr.strip()}")
            return False

        success = parse_is_ok(proc.stdout)
        if not success:
            print(f"{host} で set_ros 応答が異常です: {proc.stdout.strip()}")
        return success

    results = [run_set(host) for host in targets]
    return all(results)

# Wasanbon-Webのserver setを各ホストへ適用
def set_server(network_info, robot_path):
    print("set_server")
    if not network_info:
        raise ValueError("network_info が指定されていません。")
    if not robot_path:
        raise ValueError("robot_path が指定されていません。")

    master_ip = network_info.get("master")
    if not master_ip:
        raise ValueError("network_info に 'master' が含まれていません。")

    # ロボット設定ファイルから 'run' と 'network' のセクションを読み込む
    config = load_yaml(robot_path)
    run_section = config.get("run") or {}
    network_section = config.get("network") or []

    # network設定のホストIPをキーとして、対応するrun設定を引けるように辞書を作成
    run_by_host = {}
    if isinstance(run_section, dict):
        id_to_run = run_section
    else:
        print("run セクションの形式が想定と異なります。")
        return False

    for entry in network_section:
        pc_id = entry.get("id")
        host = entry.get("host")
        if pc_id and host and pc_id in id_to_run:
            run_by_host[host] = id_to_run[pc_id]

    # 'package_name command_name' 形式の文字列を分割するヘルパー関数
    def parse_entry(entry: str) -> Tuple[str, str]:
        parts = entry.split(maxsplit=1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    # パッケージのディレクトリをキャッシュするための辞書
    package_dir_cache: Dict[str, str] = {}

    def get_package_dir(package: str) -> Optional[str]:
        if package in package_dir_cache:
            return package_dir_cache[package]
        proc = subprocess.run(
            ["wasanbon-admin.py", "package", "directory", package],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"パッケージ {package} のディレクトリ取得に失敗しました: {proc.stderr.strip()}")
            return None
        directory = proc.stdout.strip()
        package_dir_cache[package] = directory
        return directory

    # curlコマンドのJSON応答から 'is_ok' の値を取得するヘルパー関数
    def parse_is_ok(raw_output: str) -> Optional[bool]:
        lines = [line.strip() for line in raw_output.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "is_ok" in payload:
                return bool(payload["is_ok"])
        return None

    success = True

    # --- ローカルホストの設定 (mgr.py を使用) ---
    local_host = network_info.get("local")
    local_ip = local_host
    if local_host:
        local_run = run_by_host.get(local_host)
        if not local_run:
            print(f"ローカルホスト {local_host} に対する run 設定が見つかりません。")
        else:
            # systemコマンドに対する設定
            for entry in local_run.get("system", []) or []:
                package, system_name = parse_entry(entry)
                package_dir = get_package_dir(package)
                # パッケージのディレクトリが見つからなければスキップ
                if not package_dir:
                    success = False
                    continue
                cmd = f"cd {package_dir} && ./mgr.py server set {master_ip} {local_ip}"
                if system_name:
                    cmd += f" {system_name}"
                proc = subprocess.run(
                    ["bash", "-lc", cmd],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    print(f"{entry} の server set に失敗しました: {proc.stderr.strip()}")
                    success = False

            # moduleコマンドに対する設定
            for entry in local_run.get("module", []) or []:
                package, _module_name = parse_entry(entry)
                package_dir = get_package_dir(package)
                # パッケージのディレクトリが見つからなければスキップ
                if not package_dir:
                    success = False
                    continue
                cmd = f"cd {package_dir} && ./mgr.py server set {master_ip} {local_ip}"
                proc = subprocess.run(
                    ["bash", "-lc", cmd],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode != 0:
                    print(f"{entry} の module server set に失敗しました: {proc.stderr.strip()}")
                    success = False

    # --- リモートホスト（Managed hosts）の設定 (curl を使用) ---
    managed_hosts = network_info.get("managed") or []
    for host in managed_hosts:
        run_cfg = run_by_host.get(host)
        if not run_cfg:
            print(f"managed ホスト {host} の run 設定が見つかりません。")
            success = False
            continue

        # systemコマンドに対する設定
        for entry in run_cfg.get("system", []) or []:
            package, system_name = parse_entry(entry)
            if not system_name:
                print(f"System entry {entry} に system 名が含まれていません。")
                success = False
                continue
            curl_cmd = (
                f"curl -X PUT -u admin:admin "
                f"http://{host}:8000/dev/packages/{package}/server/set/{master_ip}/{system_name}"
            )
            proc = subprocess.run(
                ["bash", "-lc", curl_cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                print(f"{host} 向け system {entry} の設定に失敗しました: {proc.stderr.strip()}")
                success = False
            else:
                is_ok = parse_is_ok(proc.stdout)
                if is_ok is False:
                    print(f"{host} 向け system {entry} の設定が失敗応答です: {proc.stdout.strip()}")
                    success = False

        # moduleコマンドに対する設定
        for entry in run_cfg.get("module", []) or []:
            package, _module_name = parse_entry(entry)
            curl_cmd = (
                f"curl -X PUT -u admin:admin "
                f"http://{host}:8000/dev/packages/{package}/server/set/{master_ip}"
            )
            proc = subprocess.run(
                ["bash", "-lc", curl_cmd],
                capture_output=True,
                text=True,
                check=False,
            )
            if proc.returncode != 0:
                print(f"{host} 向け module {entry} の設定に失敗しました: {proc.stderr.strip()}")
                success = False
            else:
                is_ok = parse_is_ok(proc.stdout)
                if is_ok is False:
                    print(f"{host} 向け module {entry} の設定が失敗応答です: {proc.stdout.strip()}")
                    success = False


    return success

# roscoreとnameserverの起動をAPIで実行
def server_start(network_info):
    print("server_start")
    if not network_info:
        raise ValueError("network_info が指定されていません。")

    master_ip = network_info.get("master")
    if not master_ip:
        raise ValueError("network_info に 'master' が含まれていません。")

    endpoints = [
        f"http://{master_ip}:8000/roscore/run",
        f"http://{master_ip}:8000/nameserver/start",
    ]

    success = True
    for url in endpoints:
        curl_cmd = f"curl -X POST -u admin:admin {url}"
        proc = subprocess.run(
            ["bash", "-lc", curl_cmd],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"{url} の起動に失敗しました: {proc.stderr.strip()}")
            success = False
        else:
            output = proc.stdout.strip()
            if output:
                print(f"{url} 応答: {output}")

    return success


# Wasanbon-Webをローカル/リモート停止
def wa_stop(network_info=None):
    print("wa_stop")
    process_waweb_path = os.path.join(os.path.dirname(__file__), "process_waweb")
    if process_waweb_path not in sys.path:
        sys.path.append(process_waweb_path)

    from auto_stop_local import stop_all_local_with_pexpect
    from auto_stop_remote import stop_remote_all

    results = {}

    managed_ips = []
    managed_users = []
    managed_pswds = []
    if network_info:
        managed_ips = network_info.get("managed") or []
        managed_users = network_info.get("managed_user") or []
        managed_pswds = network_info.get("managed_pswd") or []

    if not (len(managed_ips) == len(managed_users) == len(managed_pswds)):
        print("Warning: inconsistent managed host information; skipping incomplete entries.")

    remote_entries = []
    for host, user, pswd in zip(managed_ips, managed_users, managed_pswds):
        if not (host and user and pswd):
            print(f"Skipping remote host {host!r}: missing credentials.")
            continue
        remote_entries.append((host, user, pswd))

    total_workers = 1 + len(remote_entries)

    with ThreadPoolExecutor(max_workers=total_workers) as executor:
        futures = [("local", executor.submit(stop_all_local_with_pexpect))]
        for host, user, pswd in remote_entries:
            futures.append((host, executor.submit(stop_remote_all, host, user, pswd)))

        for key, future in futures:
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {"error": str(exc)}

    return results


# Wasanbon-Webをローカル/リモート起動
def wa_start(network_info=None):
    print("wa_start")
    process_waweb_path = os.path.join(os.path.dirname(__file__), "process_waweb")
    if process_waweb_path not in sys.path:
        sys.path.append(process_waweb_path)

    from auto_start_local import start_local
    from auto_start_remote import start_remote

    results = {}

    if not network_info:
        results["local"] = start_local()
        return results

    local_ip = network_info.get("local")
    managed_ips = network_info.get("managed") or []
    managed_users = network_info.get("managed_user") or []
    managed_pswds = network_info.get("managed_pswd") or []

    if not (len(managed_ips) == len(managed_users) == len(managed_pswds)):
        print("Warning: inconsistent managed host information; skipping incomplete entries.")

    remote_entries = []
    for host, user, pswd in zip(managed_ips, managed_users, managed_pswds):
        if not (host and user and pswd):
            print(f"Skipping remote host {host!r}: missing credentials.")
            continue
        remote_entries.append((host, user, pswd))

    total_workers = (1 if local_ip else 0) + len(remote_entries)
    if total_workers == 0:
        print("wa_start: 起動対象がありません。")
        return results

    with ThreadPoolExecutor(max_workers=total_workers) as executor:
        futures = []
        if local_ip:
            futures.append(("local", executor.submit(start_local)))
        for host, user, pswd in remote_entries:
            futures.append((host, executor.submit(start_remote, host, user, pswd)))

        for key, future in futures:
            try:
                results[key] = future.result()
            except Exception as exc:
                results[key] = {"error": str(exc)}

    return results



# ○
# CLI引数に応じた処理の分岐
def main(robot_path, service, functions):
    if len(args)>4: # 4以上の場合、自動ネットワーク設定が必要と判断
        master_ip = args[4]
        network_info = get_network_info(master_ip, robot_path)
        print(network_info)
        # wa_start(network_info)

    if args[3] == 'collect':
        ###ロボットファイルに含まれているソフトウェアを収集
        print("collect robot packages")
        collect(robot_path)

        ###必要なHRI機能に必要なソフトウェアを分析
        print("analyze modules")
        install_file = analyze(service,functions)
        print(install_file)

        ###必要なHRI機能に必要なソフトウェアを収集
        print("collect dependencies modules")
        collect(install_file)

    elif args[3] == 'build':
        print("system build")
        _build(robot_path, service)
        build(robot_path, service, network_info)

    elif args[3] == 'set':
        print("system set")
        set_network(network_info, robot_path)


    elif args[3] == 'run':
        print("system run")
        # サーバー起動
        server_start(network_info)
        if len(args)<5:
            nameserver() 
            # wa_start(network_info) #wasanbon-webframeworkサーバー自動起動関数

        ## ロボットセットアップモジュール起動
        if not process_setup(robot_path):
            return
        
        ## 他モジュール起動
        run_web(robot_path)
        print(f"HRI package {service}")
        launch_file = analyze2(service, robot_path, functions)
        run(launch_file) #上位モジュールの起動

        # user_input = input("サービスアプリケーションを実行しますか：(Y/N)")
        # if user_input == "Y" or user_input == "y":
        #     P = subprocess.Popen(["gnome-terminal", "--", "bash", "-i", "-c", "rosrun rois_env service_app4.py"])
        #     print("シナリオ動作中....")
        #     return_code = P.wait() # service_app.py の終了を待機
        #     print(f"シナリオ動作完了")
        
        time.sleep(4)
        print("サービスアプリケーションを実行")
        P = subprocess.Popen(["gnome-terminal", "--", "bash", "-i", "-c", "rosrun rois_env service_app4.py"])
        print("シナリオ動作中....")
        return_code = P.wait() # service_app.py の終了を待機
        print(f"シナリオ動作完了")
    
    elif args[3] == 'setrun':
        print("system set & run")
        ## 通信設定
        set_network(network_info, robot_path)

        ## サーバー起動
        server_start(network_info)
        if len(args)<5:
            nameserver() 
            # wa_start(network_info)   

        ## ロボットセットアップモジュール起動
        if not process_setup(robot_path):
            return
        
        ## 他モジュール起動
        run_web(robot_path)
        print(f"HRI package {service}")
        launch_file = analyze2(service, robot_path, functions)
        run(launch_file)

        time.sleep(4)
        print("サービスアプリケーションを実行")
        P = subprocess.Popen(["gnome-terminal", "--", "bash", "-i", "-c", "rosrun rois_env service_app4.py"])
        print("シナリオ動作中....")
        return_code = P.wait() # service_app.py の終了を待機
        print(f"シナリオ動作完了")

        # user_input = input("サービスアプリケーションを実行しますか：(Y/N)")
        # if user_input == "Y" or user_input == "y":
        #     P = subprocess.Popen(["gnome-terminal", "--", "bash", "-i", "-c", "rosrun rois_env service_app4.py"])
        #     print("シナリオ動作中....")
        #     return_code = P.wait() # service_app.py の終了を待機
        #     print(f"シナリオ動作完了")

    elif args[3] == 'stop':
        if args[5] == 'all':
            stop_all_processes()
        else:
            print("allか否かがわかりません")
    
    elif args[3] == 'nameserver':
        print("sytem run")
        nameserver()

    else :
        print("finish")

# ○
if __name__ == '__main__':
    # print("start")
    rtsi_dir = "RTSI_FWasanbonWeb_master"

    args = sys.argv

    print(f"ROBOT NAME :{args[1]}")    

    system_dir = f"{home_path}/{rtsi_dir}"  
    robot_path = f"{system_dir}/{args[1]}.yaml"
    scenario_path = f"{system_dir}/{args[2]}.yaml"

    service_package = load_yaml(robot_path)['collect']['engine'][0]
    functions = scenario_analyze(scenario_path)

    ### ロボットファイル・シナリオファイル・扱うサービスパッケージを用いて運用開始
    print(robot_path, service_package, functions)
    main(robot_path, service_package, functions)
