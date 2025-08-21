#!/bin/bash

# 阶段1：从sunnypilot拉取
echo "切换到sunnypilot LFS配置"
cp .lfsconfig-sunnypilot .lfsconfig
git lfs fetch --all

# 阶段2：推送到自己的LFS
echo "切换到自己的LFS配置"
cp .lfsconfig-my .lfsconfig
git lfs push mygitlab --all

# 验证
echo "验证迁移结果"
git lfs ls-files | while read -r line; do
    oid=$(echo $line | awk '{print $1}')
    if ! git lfs cat $oid > /dev/null 2>&1; then
        echo "❌ 缺失对象: $oid"
    else
        echo "✅ 对象存在: $oid"
    fi
done