// 配置你的网关地址 (如果部署在云服务器，请修改 localhost)
const GATEWAY_URL = "http://localhost:28888/api/pool/sync";

const SITES = {
    "chatgpt.com": "chatgpt",
    "claude.ai": "claude",
    "gemini.google.com": "gemini",
    "chat.deepseek.com": "deepseek",
    "kimi.moonshot.cn": "moonshot"
};

chrome.cookies.onChanged.addListener(async (info) => {
    if (info.removed) return;
    
    let domain = info.cookie.domain;
    let siteKey = null;
    
    for (let d in SITES) {
        if (domain.includes(d)) { siteKey = SITES[d]; break; }
    }
    
    if (siteKey) {
        // 获取该域下所有 Cookie
        const allCookies = await chrome.cookies.getAll({domain: domain});
        
        // 简单的 Token 提取逻辑 (示例: 提取所有 Cookie 作为凭证)
        // 实际使用中，后端 G4F 往往只需要 Cookie 字符串
        let cookieDict = {};
        allCookies.forEach(c => cookieDict[c.name] = c.value);
        
        fetch(GATEWAY_URL, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                source: siteKey,
                cookies: cookieDict,
                tokens: {} // 部分站点可能需要 LocalStorage Token，此处暂略
            })
        }).then(r => console.log("Synced", siteKey)).catch(e => console.error(e));
    }
});
