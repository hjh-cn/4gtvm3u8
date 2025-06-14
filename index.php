<?php
declare(strict_types=1);

// ─── 配置区 ────────────────────────────────────────────────────────────────
const DEFAULT_CHANNEL = 'litv-ftv13';
const PYTHON_PATH     = 'python路径';
const SCRIPT_PATH     = 'main.py的路径';
const CUSTOM_HOST     = '反代（proxy.py)的域名';

// ─── 获取并验证频道 ID ────────────────────────────────────────────────────────
$channelId = filter_input(INPUT_GET, 'id', FILTER_SANITIZE_STRING) ?: DEFAULT_CHANNEL;
if (!preg_match('/^[A-Za-z0-9\-]+$/', $channelId)) {
    http_response_code(400);
    header('Content-Type: text/plain; charset=UTF-8');
    exit("❌ 无效的频道 ID：{$channelId}");
}

// ─── 构造命令并执行 ─────────────────────────────────────────────────────────
$cmd = sprintf(
    '%s %s %s 2>&1',
    escapeshellcmd(PYTHON_PATH),
    escapeshellcmd(SCRIPT_PATH),
    escapeshellarg($channelId)
);

exec($cmd, $outputLines, $exitCode);
$output = trim(implode("\n", $outputLines));

if ($exitCode !== 0 || $output === '') {
    http_response_code(502);
    header('Content-Type: text/plain; charset=UTF-8');
    exit("❌ 无法获取播放地址（exit code: {$exitCode}）。\n详细信息：\n" . htmlspecialchars($output));
}

// ─── 解析并强制 HTTP 重定向 ────────────────────────────────────────────────────
$parts = parse_url($output);
if (!isset($parts['path'])) {
    http_response_code(500);
    header('Content-Type: text/plain; charset=UTF-8');
    exit("⚠️ 无法解析脚本输出的 URL：\n" . htmlspecialchars($output));
}

$path   = $parts['path'];
$query  = isset($parts['query'])    ? '?' . $parts['query']    : '';
$frag   = isset($parts['fragment']) ? '#' . $parts['fragment'] : '';

// 这里硬编码为 http，彻底忽略原始的 scheme
$redirectUrl = 'https://' . CUSTOM_HOST . $path . $query . $frag;

// ─── 302 重定向 ────────────────────────────────────────────────────────────────
header('Location: ' . $redirectUrl, true, 302);
exit;
