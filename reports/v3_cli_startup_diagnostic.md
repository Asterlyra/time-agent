# v3 CLI 启动诊断（受限环境）

批次 `runs/v3-pilot-20261029T140912195549Z` 首条记录为 CLIServiceError，未产生 CLI JSON 事件；原批次保留。

使用 `scripts/diagnose_mxc_startup.py` 的无私有题目、禁用工具启动请求复现：仅使用操作系统路径字段白名单时，CLI 退出码为 1、stdout 为 0 字节，stderr 命中 sandbox/generic_error/required 预定义类别。仅增加非密钥的 Windows 沙箱包标识后现象不变。受控短语分类中，require 类词与 environment、sandbox 类词在 80 个字符内出现；其他预定义类别未匹配。此结果不证明错误原因或缺少的具体配置项，不能根据词语距离做因果结论。该分类没有输出 stderr 原文、环境变量值、授权信息或模型文本。

诊断并未继承全部环境变量，也没有执行模型可调用命令的隔离探针；它不构成隔离验证。适配器尚未在白名单环境中成功连接真实模型；正式实验不应启动。
