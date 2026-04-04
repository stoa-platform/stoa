<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true displayRequiredFields=false>
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <meta name="robots" content="noindex, nofollow">
    <meta name="viewport" content="width=device-width, initial-scale=1">

    <title>${msg("loginTitle")}</title>

    <!-- Favicon -->
    <link rel="icon" type="image/png" sizes="32x32" href="${url.resourcesPath}/img/favicon.png">
    <link rel="icon" type="image/svg+xml" href="${url.resourcesPath}/img/favicon.svg">

    <!-- Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <!-- STOA Theme Styles -->
    <link href="${url.resourcesPath}/css/stoa-login.css" rel="stylesheet">
</head>

<body>
    <#nested "form">

    <!-- Footer (outside card) -->
    <div class="stoa-footer">
        <p>&copy; 2026 <a href="https://www.gostoa.dev" target="_blank">STOA Platform</a>. All rights reserved.</p>
        <div class="footer-links">
            <a href="https://docs.gostoa.dev" target="_blank">Docs</a>
            <span>&bull;</span>
            <a href="https://github.com/stoa-platform" target="_blank">GitHub</a>
            <span>&bull;</span>
            <a href="https://discord.gg/j8tHSSes" target="_blank">Discord</a>
        </div>
    </div>
</body>
</html>
</#macro>
