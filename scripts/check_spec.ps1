param(
    [Parameter(Mandatory = $true)][string]$SpecDir,
    [Parameter(Mandatory = $true)][ValidateSet('draft', 'delivery')][string]$Stage
)

$ErrorActionPreference = 'Stop'
$errors = [System.Collections.Generic.List[string]]::new()
$placeholders = @('', '无', '不适用', 'n/a', 'na', '待确认', '待填写', '未填写')
$genericEvidence = $placeholders + @('正常', '通过', '已验证', 'pass', '-', '…')
$independentActors = @('新上下文', '新 agent', '不同模型', '人工')
$strictActors = @('新 agent', '不同模型', '人工')

function Read-Text([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        $script:errors.Add("缺少文件：$Path")
        return ''
    }
    return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($false))
}

function Get-Value([string]$Text, [string]$Label) {
    $match = [regex]::Match($Text, "(?m)^[>-]\s*$([regex]::Escape($Label))：\s*(.+)$")
    if ($match.Success) { return $match.Groups[1].Value.Trim() }
    return $null
}

function Test-Unresolved([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Contains('{{')) { return $true }
    return $placeholders -contains $Value.Trim().ToLowerInvariant()
}

function Test-IndependentActor([string]$Value, [bool]$Strict = $false) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.ToLowerInvariant().Contains('同一 agent')) { return $false }
    $allowed = if ($Strict) { $strictActors } else { $independentActors }
    foreach ($actor in $allowed) { if ($Value.ToLowerInvariant().Contains($actor)) { return $true } }
    return $false
}

function Get-ACs([string]$Spec) {
    $items = @()
    foreach ($match in [regex]::Matches($Spec, '\*\*(AC-\d+)\*\*.*风险：\s*(低|中|高)(?!\s*/).*证据类型：\s*(自动化|可复现命令|浏览器|人工)(?!\s*/)')) {
        $items += [pscustomobject]@{ Id = $match.Groups[1].Value; Risk = $match.Groups[2].Value; EvidenceType = $match.Groups[3].Value }
    }
    return $items
}

function Test-Review([string]$Root, [string]$Spec, [bool]$Strict) {
    foreach ($label in @('审核者', '审核版本与输入', '审核输出引用', '独立性')) {
        if (Test-Unresolved (Get-Value $Spec $label)) { $script:errors.Add("独立审核记录未填写：$label") }
    }
    if (-not (Test-IndependentActor (Get-Value $Spec '审核者') $Strict)) { $script:errors.Add('审核者不满足所声明的独立性要求') }
    if (-not ((Get-Value $Spec '审核输出引用') -like '*session/independent-review.md*')) { $script:errors.Add('审核输出引用必须指向 session/independent-review.md') }

    $review = Read-Text (Join-Path $Root 'session\independent-review.md')
    if (-not $review) { return }
    $version = Get-Value $Spec 'Spec 版本'
    foreach ($label in @('审核的 Spec', '审核者', '审核来源', '输入范围', '独立性声明')) {
        if (Test-Unresolved (Get-Value $review $label)) { $script:errors.Add("独立审核文件未填写：$label") }
    }
    if ($version -and -not ((Get-Value $review '审核的 Spec') -like "*$version*")) { $script:errors.Add("独立审核文件版本不匹配：需要 $version") }
    if (-not (Test-IndependentActor (Get-Value $review '审核者') $Strict)) { $script:errors.Add('独立审核文件的审核者不具备独立性') }
    if (-not ((Get-Value $review '独立性声明') -like '*未读取起草过程*')) { $script:errors.Add('独立审核文件缺少未读取起草过程的声明') }
    $conclusion = Get-Value $review '结论'
    if ((Test-Unresolved $conclusion) -or $conclusion.Contains('阻塞')) { $script:errors.Add('独立审核文件没有有效的非阻塞结论') }
    $independence = Get-Value $Spec '独立性'
    if ($Strict -and $independence -and $independence.Contains('未独立')) { $script:errors.Add('Strict 不能以未独立状态通过审核') }
}

function Test-RiskMapping([string]$Spec, $Acs) {
    $mapping = @{}
    foreach ($match in [regex]::Matches($Spec, '(?m)^-\s*KR-\d+\s*\[([^]]+)\]\s*→\s*(.+)$')) {
        $kind = $match.Groups[1].Value
        if ($kind.Contains('/') -or $kind.Contains('{{')) { continue }
        $mapping[$kind] = [regex]::Matches($match.Groups[2].Value, 'AC-\d+') | ForEach-Object { $_.Value }
    }
    $riskTerms = @{ '数据写入/删除' = @('数据写入', '写入', '删除'); '权限/敏感数据' = @('权限', '敏感'); '外部副作用' = @('外部', '副作用'); '不可逆' = @('不可逆') }
    $highIds = @($Acs | Where-Object { $_.Risk -eq '高' } | ForEach-Object { $_.Id })
    foreach ($surface in $riskTerms.Keys) {
        if ($Spec -notmatch "(?m)^-\s*$([regex]::Escape($surface))：\s*是\s*$") { continue }
        $ids = @()
        foreach ($kind in $mapping.Keys) {
            if (@($riskTerms[$surface] | Where-Object { $kind.Contains($_) }).Count -gt 0) { $ids += $mapping[$kind] }
        }
        if ($ids.Count -eq 0) { $script:errors.Add("高风险变更面缺少关键风险映射：$surface") }
        elseif (@($ids | Where-Object { $highIds -notcontains $_ }).Count -gt 0) { $script:errors.Add("关键风险映射必须指向高风险 AC：$surface") }
    }
}

function Test-Confirmation([string]$Spec) {
    $version = Get-Value $Spec 'Spec 版本'
    $confirmation = Get-Value $Spec '用户确认'
    if (Test-Unresolved $confirmation) { $script:errors.Add('用户确认未填写') }
    elseif (-not $confirmation.Contains($version)) { $script:errors.Add("用户确认未关联当前 Spec 版本：需要 $version") }
    if ((Get-Value $Spec '审核状态').Contains('未独立') -and -not $confirmation.Contains('接受未独立')) { $script:errors.Add('未独立审核必须获得用户明确接受') }
}
function Test-DeliveryReview([string]$Root, [string]$Spec) {
    $review = Read-Text (Join-Path $Root 'check_reports\delivery-review.md')
    if (-not $review) { return }
    foreach ($label in @('审核的 Spec','审核者','审核范围','审核来源')) { if (Test-Unresolved (Get-Value $review $label)) { $script:errors.Add("交付审核未填写：$label") } }
    if ([string]::IsNullOrWhiteSpace((Get-Value $review '审核结论')) -or (Get-Value $review '审核结论').Contains('{{')) { $script:errors.Add('交付审核未填写：审核结论') }
    $version = Get-Value $Spec 'Spec 版本'
    if ($version -and -not ((Get-Value $review '审核的 Spec') -like "*$version*")) { $script:errors.Add("交付审核版本不匹配：需要 $version") }
    $conclusion = Get-Value $review '审核结论'
    if (-not $conclusion.Contains('通过') -or $conclusion.Contains('阻塞') -or $conclusion.Contains('退回') -or $conclusion.Contains('不通过')) { $script:errors.Add('交付审核未通过') }
}
$spec = Read-Text (Join-Path $SpecDir 'spec.md')
if ($spec) {
    foreach ($label in @('Spec 版本', '原始需求', '审核状态')) {
        if (Test-Unresolved (Get-Value $spec $label)) { $errors.Add("Spec 元数据未填写：$label") }
    }
    $acs = @(Get-ACs $spec)
    if ($acs.Count -eq 0) { $errors.Add('未找到带风险和证据类型的 AC') }
    if (@($acs.Id | Select-Object -Unique).Count -ne $acs.Count) { $errors.Add('AC 编号重复') }
    Test-RiskMapping $spec $acs
    $status = (Get-Value $spec '审核状态').ToLowerInvariant()
    $strict = $spec.Contains('流程档位：Strict')
    if ($strict -or $status.Contains('fresh review') -or $status.Contains('人工复查')) { Test-Review $SpecDir $spec $strict }
}

if ($Stage -eq 'delivery' -and $spec) {
    Test-Confirmation $spec
    Test-DeliveryReview $SpecDir $spec
    $tasks = Read-Text (Join-Path $SpecDir 'tasks.md')
    $report = Read-Text (Join-Path $SpecDir 'check_reports\harness-check.md')
    $requiredIds = [System.Collections.Generic.HashSet[string]]::new()
    foreach ($line in $tasks -split "`r?`n") {
        $match = [regex]::Match($line, '- \[[ xX]\] \*\*T-\d+\*\* \[(required|optional)\].*?→\s*(.+)')
        if (-not $match.Success) { continue }
        $kind, $linked = $match.Groups[1].Value, $match.Groups[2].Value
        $ids = [regex]::Matches($linked, 'AC-\d+') | ForEach-Object { $_.Value }
        if ($kind -eq 'required') {
            if (-not ($line.StartsWith('- [x]') -or $line.StartsWith('- [X]'))) { $errors.Add("必需任务未完成：$line") }
            foreach ($id in $ids) { [void]$requiredIds.Add($id) }
        } elseif (@($ids | Where-Object { $acs.Id -contains $_ }).Count -gt 0) { $errors.Add("optional 任务不得引用当前 AC：$line") }
    }
    foreach ($ac in $acs) { if (-not $requiredIds.Contains($ac.Id)) { $errors.Add("AC 未映射到 required 任务：$($ac.Id)") } }

    $outcomes = @{}
    foreach ($line in $report -split "`r?`n") {
        $cells = @($line.Trim().Trim('|').Split('|') | ForEach-Object { $_.Trim() })
        if ($cells.Count -lt 4 -or $cells[0] -notmatch '^AC-\d+$') { continue }
        $id, $result, $type, $evidence = $cells[0], $cells[1], $cells[2], $cells[3]
        if ($outcomes.ContainsKey($id)) { $errors.Add("检查报告中的 AC 重复：$id"); continue }
        if (@('pass','fail','partial','skipped') -notcontains $result) { $errors.Add("AC 结果非法：$id = $result"); continue }
        if (@('自动化','可复现命令','浏览器','人工') -notcontains $type) { $errors.Add("AC 证据类型非法：$id = $type") }
        $artifact = [regex]::Match($evidence, '(?i)(?:文件|file)\s*[:：]\s*([^\s#；;|]+)')
        $summary = [regex]::Replace($evidence, '(?i)(?:文件|file)\s*[:：]\s*([^\s#；;|]+)', '').Trim(' ', '；', ';', '，', ',')
        if ($genericEvidence -contains $summary.ToLowerInvariant() -or $evidence.Contains('{{')) { $errors.Add("AC 证据为空或过于泛化：$id") }
        if (-not $artifact.Success) { $errors.Add("AC 证据缺少文件引用：$id") }
        else {
            $rootPath = [System.IO.Path]::GetFullPath($SpecDir)
            $artifactPath = [System.IO.Path]::GetFullPath((Join-Path $SpecDir $artifact.Groups[1].Value))
            if (-not $artifactPath.StartsWith($rootPath + [System.IO.Path]::DirectorySeparatorChar) -or -not (Test-Path -LiteralPath $artifactPath -PathType Leaf) -or (Get-Item -LiteralPath $artifactPath).Length -eq 0) { $errors.Add("AC 证据文件不存在、为空或超出任务目录：$id") }
        }
        $outcomes[$id] = @($result, $type)
    }
    foreach ($ac in $acs) {
        if (-not $outcomes.ContainsKey($ac.Id)) { $errors.Add("检查报告缺少 AC：$($ac.Id)"); continue }
        $result, $type = $outcomes[$ac.Id]
        if ($result -ne 'pass') { $errors.Add("AC 未通过：$($ac.Id) = $result") }
        elseif ($type -ne $ac.EvidenceType) { $errors.Add("AC 证据类型不匹配：$($ac.Id) 需要 $($ac.EvidenceType)，实际 $type") }
        elseif ($ac.Risk -eq '高' -and $type -eq '人工') { $errors.Add("高风险 AC 不得只使用人工证据：$($ac.Id)") }
    }
    if ($tasks -notmatch '(?m)^- 状态：待交付\r?$') { $errors.Add('tasks.md 尚未标记为待交付') }
}

if ($errors.Count -gt 0) {
    [Console]::Error.WriteLine('Spec 检查失败：')
    $errors | ForEach-Object { [Console]::Error.WriteLine("- $_") }
    exit 1
}
Write-Output "Spec 检查通过：$SpecDir ($Stage)"
