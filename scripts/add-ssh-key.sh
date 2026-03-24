#!/bin/bash

# 添加 SSH key 到飞牛 NAS
# 请以 jieliu 用户登录 NAS 后执行此脚本

# 确保 .ssh 目录存在
mkdir -p ~/.ssh

# 设置正确的权限
chmod 700 ~/.ssh

# 添加 SSH key 到 authorized_keys
# （如果 key 已存在，不会重复添加）
if ! grep -q "jieliu@foxnas" ~/.ssh/authorized_keys 2>/dev/null; then
    echo "Adding SSH key to authorized_keys..."
    echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDvcPxZhQyFfbh/uy2cC004YN7FzdaElFfT1eurJCIB0 jieliu@foxnas" >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    echo "SSH key added successfully!"
else
    echo "SSH key already exists in authorized_keys"
fi

echo ""
echo "Current SSH keys:"
cat ~/.ssh/authorized_keys
