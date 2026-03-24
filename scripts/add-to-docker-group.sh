#!/bin/bash

# 飞牛 NAS 部署 noctra - 第一步：添加用户到 docker 组

echo "================================"
echo "将用户 jieliu 添加到 docker 组"
echo "================================"
echo ""

echo "执行以下命令（需要 sudo 密码）："
echo "sudo usermod -aG docker jieliu"
echo ""

echo "添加完成后，请执行以下命令使权限生效："
echo "方法 1：退出并重新登录"
echo "方法 2：或执行 newgrp docker"
echo ""

echo "验证是否添加成功："
echo "groups jieliu | grep docker"
echo ""

echo "================================"
echo "添加成功后，告诉我 '添加完成'"
echo "我会继续部署 noctra"
echo "================================"
