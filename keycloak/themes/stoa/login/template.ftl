<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html<#if realm.internationalizationEnabled> lang="${locale.currentLanguageTag}"</#if>>
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
    <meta name="robots" content="noindex, nofollow">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>${msg("loginTitle",(realm.displayName!'STOA Platform'))}</title>

    <!-- Favicon -->
    <link rel="icon" type="image/svg+xml" href="${url.resourcesPath}/img/favicon.svg">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <!-- STOA Theme Styles -->
    <link href="${url.resourcesPath}/css/stoa-login.css" rel="stylesheet" />

    <#if properties.meta?has_content>
        <#list properties.meta?split(' ') as meta>
            <meta name="${meta?split('==')[0]}" content="${meta?split('==')[1]}"/>
        </#list>
    </#if>
</head>

<body class="${bodyClass}">
    <!-- Login Card -->
    <div class="login-card">
        <!-- Header -->
        <#if !(auth?has_content && auth.showUsername() && !auth.showResetCredentials())>
            <#nested "header">
        <#else>
            <#nested "show-username">
            <div class="stoa-header">
                <div class="stoa-badge">Open Source • Apache 2.0</div>
                <div class="stoa-logo">
                    <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <rect width="40" height="40" rx="8" fill="white" fill-opacity="0.15"/>
                        <path d="M12 14h16v2H12v-2zm0 5h16v2H12v-2zm0 5h10v2H12v-2z" fill="white"/>
                        <circle cx="30" cy="26" r="4" fill="white" fill-opacity="0.8"/>
                    </svg>
                    <span class="stoa-logo-text">STOA</span>
                </div>
                <div id="kc-username" class="logged-user">
                    <span>${auth.attemptedUsername}</span>
                    <a id="reset-login" href="${url.loginRestartFlowUrl}" aria-label="Restart login">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M19 12H5M12 19l-7-7 7-7"/>
                        </svg>
                    </a>
                </div>
            </div>
        </#if>

        <!-- Messages/Alerts -->
        <#if displayMessage && message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
            <div class="alert alert-${message.type}">
                <#if message.type = 'success'><span class="alert-icon">✓</span></#if>
                <#if message.type = 'warning'><span class="alert-icon">⚠</span></#if>
                <#if message.type = 'error'><span class="alert-icon">✕</span></#if>
                <#if message.type = 'info'><span class="alert-icon">ℹ</span></#if>
                <span class="alert-text">${kcSanitize(message.summary)?no_esc}</span>
            </div>
        </#if>

        <!-- Main Content -->
        <div class="login-content">
            <#nested "form">
        </div>

        <!-- Info Section -->
        <#if displayInfo>
            <#nested "info">
        </#if>
    </div>

    <!-- Footer (outside card) -->
    <div class="stoa-footer">
        <p>© 2026 <a href="https://www.gostoa.dev" target="_blank">STOA Platform</a>. All rights reserved.</p>
        <div class="footer-links">
            <a href="https://docs.gostoa.dev" target="_blank">Docs</a>
            <span>•</span>
            <a href="https://github.com/stoa-platform" target="_blank">GitHub</a>
            <span>•</span>
            <a href="https://discord.gg/j8tHSSes" target="_blank">Discord</a>
        </div>
    </div>

    <#if scripts??>
        <#list scripts as script>
            <script src="${script}" type="text/javascript"></script>
        </#list>
    </#if>
</body>
</html>
</#macro>
