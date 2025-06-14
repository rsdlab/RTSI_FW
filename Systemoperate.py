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

BASH = '/bin/bash'
home_path = os.environ['HOME']
ros_ws = os.environ['ROS_WS']
rtm_ws = os.environ['RTM_WS']


############################## YAML形式のシナリオファイルの読み込み ##############################
def load_yaml(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        return yaml.safe_load(file)

def join_yaml(_list, item):
    _list.append(item)
    return _list

############################### スクリプトの依存関係を解析 ##############################
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

    ros_module_to_package = {
        'moveit_commander': 'moveit',  
        'cv_bridge': 'cv-bridge',
        'ros_control': 'ros-controllers',
        'ros_arduino_bridge': 'ros_arduino_bridge'
    }

    standard_libs_path = sysconfig.get_paths()["stdlib"]

    def is_apt_installable(module_name):
        """APTでインストール可能かどうかを確認"""
        try:
            result = subprocess.run(
                ["apt-cache", "search", module_name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            return bool(result.stdout.strip())  
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

        if response.status_code == 200:
            return True         

        else:
            return False

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
    imported_modules = list(set(imported_modules))

    standard_dependencies = []
    ros_dependencies = []
    ros_add_dependencies = []
    external_dependencies = []

    ros_modules_add_translated = [ros_module_to_package.get(module, module) for module in ros_modules_add]

    for module in imported_modules:
        if module in ros_modules:
            ros_dependencies.append(module)
        elif module in ros_modules_add:  
            package_name = ros_module_to_package.get(module, module)
            ros_add_dependencies.append(package_name) 
        elif is_standard_lib(module):
            standard_dependencies.append(module)
        else:
            external_dependencies.append(module)
    pip_installable = []
    apt_installable = []
    not_pip_installable = []

    for original_module, pip_name in special_modules.items():
        if original_module in imported_modules:  
            if is_pip_installable(pip_name):
                pip_installable.append(pip_name)  
            else:
                not_pip_installable.append(original_module)

    for module in external_dependencies:
        if module not in special_modules and module in imported_modules:  
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
        "ros_additional_libraries": ros_add_dependencies,  
        "pip_installable": pip_installable,
        "apt_installable": apt_installable,
        "not_pip_installable": not_pip_installable,
    }


############################### スクリプトの依存関係を追加 ##############################
def update_yaml_with_dependencies(yaml_path1, dependencies , yaml_path2):
    """ 既存のYAMLに新しい依存関係を追加 """
    existing_data = load_yaml(yaml_path1) if os.path.exists(yaml_path1) else {}
    if os.path.exists(yaml_path1):
        with open(yaml_path1, 'r') as yaml_file:
            existing_data = yaml.safe_load(yaml_file) or {}
    else:
        existing_data = {}

    if "collect" in existing_data:
        existing_data["collect"]["rtm"].extend(dependencies["collect"]["rtm"])
        existing_data["collect"]["apt"].extend(dependencies["collect"]["apt"])
        existing_data["collect"]["pip"].extend(dependencies["collect"]["pip"])
        existing_data["collect"]["git"].extend(dependencies["collect"]["git"])
        existing_data["collect"]["other"].extend(dependencies["collect"]["other"])
    else:
        existing_data["collect"] = dependencies["collect"]

    with open(yaml_path2, 'w') as yaml_file:
        yaml.dump(existing_data, yaml_file, sort_keys=False,default_flow_style=False, allow_unicode=True)

    return yaml_path2


def filter_empty_items(items):
    """ 空の値を除外するヘルパー関数 """
    if isinstance(items, list):
        return [item for item in items if item is not None]
    elif isinstance(items, dict):
        return {k: v for k, v in items.items() if v is not None}
    return items

def load_yaml(file):
    """ YAMLファイルを読み込むヘルパー関数（仮定） """
    with open(file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def combined_collectfile(files):
    """ 複数のYAMLファイルを統合する（collect用） """

    combined_file = 'combined_collect.yaml'
    combined_data = {'collect': {key: [] for key in ["rtm", "apt", "pip", "git", "other"]}}

    for file in files:
        data = load_yaml(file)
        for key in ["rtm", "apt", "pip", "other"]:
            combined_data['collect'][key] = list(set(combined_data['collect'][key] + data.get('collect', {}).get(key, [])))
        combined_data['collect']['git'].extend(repo for repo in data.get('collect', {}).get('git', []) if repo.get('url'))

    with open(combined_file, 'w', encoding='utf-8') as output_file:
        yaml.dump(combined_data, output_file, allow_unicode=True, sort_keys=False)

    print("統合が完了しました！")

    return combined_file


# run用のyamlを合成する関数
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

    
# yamlファイルを編集(項目の削除)
def item_replace_null(output_file, route_key, keys_to_replace):
    
    with open(output_file, 'r') as infile:
        data = yaml.safe_load(infile)

    if route_key in data:
        for key in keys_to_replace:
            if key in data[route_key]:
                data[route_key][key] = [None] 

    with open(output_file, "w") as file:
        yaml.dump(data, file, default_flow_style=False)

    return output_file


# hri-c用のlaunchのyamlを作成する
def update_yaml_launch_file(launch_files):
    
    script_path = os.path.join(home_path, rtsi_dir)
    os.chdir(script_path)

 
    subprocess.run(["pwd"])

    output_file = "seed_hri.yaml"
    keys_to_replace = ['rtm','roslaunch', 'rosrun']
    route_key = 'run'

    output_file = item_replace_null(output_file, route_key, keys_to_replace)
    
    with open(output_file , 'r') as infile:
        data = yaml.safe_load(infile)

    data['run']['rtm'] = [item for item in data['run']['rtm'] if item is not None]
    data['run']['roslaunch'] = [item for item in data['run']['roslaunch'] if item is not None]
    data['run']['rosrun'] = [item for item in data['run']['rosrun'] if item is not None]

    for script in launch_files:
        if '.launch' in script:
            if script not in data['run']['roslaunch']: 
                data['run']['roslaunch'].append(script)
        else:
            if script not in data['run']['rosrun']:  
                data['run']['rosrun'].append(script)

    with open(output_file, 'w') as outfile:
        yaml.dump(data, outfile, sort_keys=False, default_flow_style=False)

    print(f"'run' section has been written to {output_file}")
    
    return output_file

# 分析のメイン処理(collect)
def analyze(engine,functions):

    collect_list = []

    for launch_file in functions:    
        print(f"HRI機能: {launch_file}")

    if engine == "None":
        return None

    files_list = [os.path.join(home_path, "catkin_ws", "src", engine, "yaml", f"{file}.yaml") for file in functions]

    return combined_collectfile(files_list)



################################ 分析のメイン処理(run) ###############################
def analyze2(engine_name, robot_path, functions):

    hri_script = []
    launch_list = []

    print(f"使用するHRI-Component {functions}")

    if functions[0] == None:
        print("pass")
    else:
        enginefile = get_enginefile(engine_name)
        hri_script = join_yaml(hri_script, enginefile)

        for launch_file in functions:
            _file = engine_name + ' ' + launch_file + ".py"
            hri_script = join_yaml(hri_script, _file)
  
    yaml_file = update_yaml_launch_file(hri_script)

    launch_list = join_yaml(launch_list, yaml_file)

    aaa = combined_runfile(launch_list) 

    return aaa

############################### Engineのノード名を取得する ###############################
def get_enginefile(engine_name):
    print(engine_name)
    directory = ros_ws + "/src/" + engine_name + "/hri.xml"

    tree = ET.parse(directory)
    root = tree.getroot()
    namespaces = {
        'gml': 'http://example.com/r/gml',
        'rois': 'http://example.com/r/rois'
    }

    filename = root.find('gml:filename', namespaces)
    if filename is not None:
        filename_text = filename.text + ".py" 
        engine = engine_name +' ' + filename_text
        return engine
    else:
        return "None"
    
def collect(yml_path):

    if  yml_path == None:
        return
    with open(yml_path , 'r') as yml:
        config = yaml.safe_load(yml)
    
 ######### wasanbon repository #####################    
    os.chdir(rtm_ws)
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
    dir_name = f"{ros_ws}/src" 
    os.chdir(dir_name)

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
        if (dec_b == 'Destination_gui'):  
            print("move system file")   
            move_file()
        else:
            print("move file for navigation")
    
 ######### add package ######################
        dec = config['collect']['rtm'][0]

        if (dec == 'MobileRobotControl'):  
            print("install sfml")      
            sfml()
        else:
            print("not install sfml")


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

def build(yml_path,service):
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

 ######### Build rtm package #####################
    leng_rtm = config['collect']['rtm']
    length_rtm = len(leng_rtm)
    for i in range(length_rtm):
        was_rep1 = config['collect']['rtm'][i]
        dir_name = f"{rtm_ws}/{was_rep1}" 
        os.chdir(dir_name)
        print('Package build {}'.format(was_rep1))
        call(['./mgr.py', 'rtc', 'build', 'all','-v'])
        

######### Start name server ##################### 
def nameserver():
    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    matching_lines = [line for line in result.stdout.splitlines() if "rosmaster" in line and "grep" not in line]
    if not len(matching_lines) > 0:
        print("roscoreが起動していません。roscoreを起動します...")
        call(["gnome-terminal", "--", "roscore"])

        time.sleep(0.5)

    else:
        print("roscoreはすでに起動しています．")

    result = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    matching_lines = [line for line in result.stdout.splitlines() if "omni" in line and "grep" not in line]
    print(len(matching_lines))

    if not len(matching_lines) > 0:
        print("nameserverが起動していません。namaserverを起動します...")
        result = subprocess.run(["locale"], capture_output=True, text=True)
        matching_lines = [line for line in result.stdout.splitlines() if "en" in line]

        username = os.environ['USER']
        child = pexpect.spawn("wasanbon-admin.py nameserver start", encoding='utf-8')
        if not len(matching_lines) > 0:
            child.expect(f"{username} のパスワード:")
        else:
            child.expect(f"password for {username}:")

        child.sendline(username)
        child.interact()

    else:
        print("nameserverはすでに起動しています．")

def run(yml_path = None):
    processes = {}

    print(yml_path)

    if yml_path is None:
        with open(args[1] , 'r') as yml:
            config = yaml.safe_load(yml)
    else:
        with open(yml_path , 'r') as yml:
            config = yaml.safe_load(yml)

    print("roslaunch")

    if 'roslaunch' in config['run']:
        leng_launch = config['run']['roslaunch']
    else:
        print("No ROS_LAUNCH module")
        return None

    if leng_launch is None:
        pass
    else:
        for index, launch_cmd in enumerate(leng_launch):
            try:
                proc = subprocess.Popen(["gnome-terminal", "--tab", "--", "bash", "-c", f"roslaunch {launch_cmd}"])
                processes[f"roslaunch_{index}"] = proc.pid  

            except OSError as e:
                print(f"Failed to start roslaunch process {launch_cmd}: {e}")
                continue  

    print("rosrun")

    if 'rosrun' in config['run']:
        leng_run = config['run']['rosrun']
    else:
        print("No ROS_RUN module")
        return None

    if leng_run is None:
        pass
    else:
        for index, run_cmd in enumerate(leng_run):
            try:
                proc = subprocess.Popen(["gnome-terminal", "--tab", "--", "bash", "-c", f"rosrun {run_cmd}"])
                processes[f"rosrun_{index}"] = proc.pid  

            except OSError as e:
                print(f"Failed to start rosrun process {run_cmd}: {e}")
                continue  
    
    print("launch rtm packages")

    if 'rtm' in config['run']:
        leng_rtm = config['run']['rtm']
    else:
        print("No RTM module")
        return None

    if leng_rtm is None:
        pass
    else:
        leng_rtm = len(leng_rtm)   

        for index in range(leng_rtm):

            was_rep1  = config['run']['rtm'][index]
            print(was_rep1)

            command = ["wasanbon-admin.py", "package", "directory_show" f"{was_rep1}"]
            dir_name = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = dir_name.communicate()
            stdout = stdout.decode('utf-8').strip()
            os.chdir(str(stdout))

            command = "./mgr.py system run -v"
            P = subprocess.Popen(["gnome-terminal", "--tab", "--", "bash", "-c", command])

# YAMLからシナリオを読み込みサービス名とタスクを抽出する
def scenario_analyze(scenario_path):
   
    os.chdir(system_dir)

    scenario_data = load_yaml(scenario_path)
    scenario = scenario_data.get('scenario', [])

    tasks = []
    functions = []
    for task in scenario:
        task_name = task.get('task', '')
        task_arg = task.get('arg', '')

        tasks.append((task_name, task_arg))

        if task_name not in functions:
            functions.append(task_name)
        else:
            pass

    return functions

def stop_all_processes():
    subprocess.call(["rosnode", "kill", "-a"])

def main(robot_path, service, functions):
    if args[3] == 'collect':
        print("collect robot packages")
        collect(robot_path)

        print("analyze modules")
        install_file = analyze(service,functions)
        print(install_file)

        print("collect dependencies modules")
        collect(install_file)

    elif args[3] == 'build':
        print("system build")
        build(robot_path, service)

    elif args[3] == 'run':
        print("sytem run")
        nameserver()
        run(robot_path)
        
        print(f"HRI package {service}")

        launch_file = analyze2(service, robot_path, functions)
        
        run(launch_file)

        user_input = input("サービスアプリケーションを実行しますか：(Y/N)")
        if user_input == "Y" or user_input == "y":
            P = subprocess.Popen(["gnome-terminal", "--", "bash", "-c", "rosrun rois_env service_app.py"])

    elif args[3] == 'stop':
        stop_all_processes()
    
    elif args[3] == 'nameserver':
        print("sytem run")
        nameserver()

    else :
        print("finish")

if __name__ == '__main__':
    print("start")
    rtsi_dir = "RTSI_FW"

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