#!/usr/bin/env node
/**
 * 配置 GitHub Repository Secrets
 * 用法: GITHUB_TOKEN=xxx node setup-github-secrets.js
 */

const https = require('https');
const fs = require('fs');
const path = require('path');
const os = require('os');

const OWNER = 'sammmad001';
const REPO = 'Questra-Search';
const API_HOST = 'api.github.com';

// 需要配置的 secrets
const SECRETS = {
  ECS_SSH_PRIVATE_KEY: {
    file: path.join(os.homedir(), '.ssh', 'id_ed25519'),
    description: 'ECS root SSH 私钥',
  },
};

async function githubRequest(method, urlPath, token, body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: API_HOST,
      path: urlPath,
      method,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'Questra-Search-CI-Setup',
      },
    };

    if (body) {
      options.headers['Content-Type'] = 'application/json';
    }

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed });
        } catch {
          resolve({ status: res.statusCode, data });
        }
      });
    });

    req.on('error', reject);

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

async function encryptSecret(publicKey, secretValue) {
  const sodium = require('libsodium-wrappers');
  await sodium.ready;

  const keyBytes = Buffer.from(publicKey, 'base64');
  const secretBytes = Buffer.from(secretValue, 'utf8');

  const encrypted = sodium.crypto_box_seal(secretBytes, keyBytes);
  return Buffer.from(encrypted).toString('base64');
}

async function main() {
  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    console.error('❌ 请设置 GITHUB_TOKEN 环境变量');
    console.error('   export GITHUB_TOKEN=ghp_xxxxxxxxxxxx');
    console.error('');
    console.error('   获取 Token: https://github.com/settings/tokens');
    console.error('   需要权限: repo, workflow');
    process.exit(1);
  }

  // 验证 token
  console.log('🔍 验证 GitHub Token...');
  const { status: authStatus, data: authData } = await githubRequest('GET', '/user', token);
  if (authStatus !== 200) {
    console.error(`❌ Token 无效: ${authData.message || authStatus}`);
    process.exit(1);
  }
  console.log(`  ✓ 已认证为: ${authData.login}`);

  // 获取仓库公钥
  console.log('\n🔑 获取仓库公钥...');
  const { status: keyStatus, data: keyData } = await githubRequest(
    'GET',
    `/repos/${OWNER}/${REPO}/actions/secrets/public-key`,
    token
  );
  if (keyStatus !== 200) {
    console.error(`❌ 获取公钥失败: ${keyData.message}`);
    process.exit(1);
  }
  console.log(`  ✓ 公钥 ID: ${keyData.key_id}`);

  // 配置每个 secret
  for (const [name, config] of Object.entries(SECRETS)) {
    console.log(`\n📝 配置 Secret: ${name} (${config.description})`);

    let secretValue;
    if (config.file) {
      if (!fs.existsSync(config.file)) {
        console.error(`  ❌ 文件不存在: ${config.file}`);
        continue;
      }
      secretValue = fs.readFileSync(config.file, 'utf8').trim();
      console.log(`  ✓ 从文件读取: ${config.file}`);
    } else if (config.value) {
      secretValue = config.value;
    } else {
      console.error(`  ❌ 未指定 secret 来源`);
      continue;
    }

    if (!secretValue) {
      console.error(`  ❌ Secret 值为空`);
      continue;
    }

    // 加密
    const encrypted = await encryptSecret(keyData.key, secretValue);

    // 设置 secret
    const { status: setStatus } = await githubRequest(
      'PUT',
      `/repos/${OWNER}/${REPO}/actions/secrets/${name}`,
      token,
      {
        encrypted_value: encrypted,
        key_id: keyData.key_id,
      }
    );

    if (setStatus === 201 || setStatus === 204) {
      console.log(`  ✅ ${name} 配置成功`);
    } else {
      console.error(`  ❌ ${name} 配置失败 (HTTP ${setStatus})`);
    }
  }

  console.log('\n============================================');
  console.log('  ✅ GitHub Secrets 配置完成');
  console.log('============================================');
  console.log('');
  console.log('已配置的 Secrets:');
  console.log('  • ECS_SSH_PRIVATE_KEY — ECS root SSH 私钥');
  console.log('');
  console.log('下一步:');
  console.log('  1. 在 GitHub 创建 production Environment:');
  console.log(`     https://github.com/${OWNER}/${REPO}/settings/environments`);
  console.log('  2. CI/CD 将在下次 push 到 main 时自动触发');
}

main().catch((err) => {
  console.error('❌ 脚本执行失败:', err.message);
  process.exit(1);
});
