#!/bin/zsh
set -uo pipefail

task_root=${0:A:h}
cd "$task_root" || exit 1
mkdir -p "$task_root/work/.cache"
task_temporary=$(mktemp -d "$task_root/work/.cache/launch.XXXXXXXX") || exit 1
trap 'rm -rf -- "$task_temporary"' EXIT
export TMPDIR="$task_temporary"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$task_root/src"
task_prefix="$task_root/.conda/campusroute"
task_python="$task_prefix/bin/python"
task_repair=0
case "${1:-}" in
    '') ;;
    --upgrade|--repair) task_repair=1 ;;
    *) print '用法：./CampusRoute.command [--upgrade|--repair]'; exit 2 ;;
esac

task_environment_ready() {
    if [[ ! -x "$task_python" ]]; then
        print '项目环境中没有可执行的 Python，需要安装环境。'
        return 1
    fi
    "$task_python" -B "$task_root/tools/check_environment.py" --backend ios || return 1
    "$task_python" -B -m pip --no-cache-dir --disable-pip-version-check check
}

if [[ "$task_repair" == '1' ]] || ! task_environment_ready >"$task_temporary/environment.txt" 2>&1; then
    if [[ "$task_repair" == '0' ]]; then
        print '环境检查未通过：'
        cat "$task_temporary/environment.txt"
        print '1  安装／升级／修复环境'
        print '0  退出'
        read -r 'task_reply?请选择数字并按回车：'
        if [[ "$task_reply" != '1' ]]; then
            exit 0
        fi
    fi
    if ! command -v conda >/dev/null 2>&1; then
        print '安装或修复需要 Miniconda。请按照 README 安装，并在 Terminal 中启用 conda。'
        read -r 'task_reply?按回车关闭窗口。'
        exit 1
    fi
    if [[ -d "$task_prefix/conda-meta" ]]; then
        task_action=update
    else
        task_action=create
    fi
    if ! conda env "$task_action" --prefix "$task_prefix" --file "$task_root/environment.yml"; then
        print '安装未完成。请根据上方错误检查网络和 Miniconda 配置，再次打开后选择1继续。'
        read -r 'task_reply?按回车关闭窗口。'
        exit 1
    fi
    "$task_python" -B -m pip install --no-cache-dir -e '.[ios]' || exit 1
    if ! task_environment_ready; then
        print '环境校验未通过。请根据上方错误完成处理，再次打开后选择1继续。'
        read -r 'task_reply?按回车关闭窗口。'
        exit 1
    fi
fi

print '在家里我们就练起来'
if /usr/bin/caffeinate -is "$task_python" -B -m campusroute --root "$task_root"; then
    exit 0
else
    task_status=$?
    read -r 'task_reply?按回车关闭窗口。'
    exit "$task_status"
fi
