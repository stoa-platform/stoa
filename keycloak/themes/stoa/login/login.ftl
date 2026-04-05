<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=true displayInfo=(realm.password && realm.registrationAllowed); section>
    <#if section = "form">
    <!-- Login Card -->
    <div class="login-card">
        <!-- Header -->
        <div class="stoa-header">
            <div class="stoa-badge">Open Source &bull; Apache 2.0</div>
            <div class="stoa-logo">
                <svg viewBox="0 0 40 40" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect width="40" height="40" rx="8" fill="white" fill-opacity="0.15"/>
                    <path d="M12 14h16v2H12v-2zm0 5h16v2H12v-2zm0 5h10v2H12v-2z" fill="white"/>
                    <circle cx="30" cy="26" r="4" fill="white" fill-opacity="0.8"/>
                </svg>
                <span class="stoa-logo-text">STOA</span>
            </div>
            <p class="stoa-tagline">${msg("loginTitleHtml")}</p>
        </div>

        <!-- Messages/Alerts -->
        <#if message?has_content && (message.type != 'warning' || !isAppInitiatedAction??)>
        <div class="login-content">
            <div class="alert alert-${message.type}">
                ${kcSanitize(message.summary)?no_esc}
            </div>
        </div>
        </#if>

        <!-- Main Content -->
        <div class="login-content">
        <#if realm.password>
        <div id="kc-form">
            <div id="kc-form-wrapper">
                    <form id="kc-form-login" onsubmit="login.disabled = true; return true;" action="${url.loginAction}" method="post">
                        <div class="form-group">
                            <label for="username">
                                <#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if>
                            </label>
                            <input tabindex="1" id="username" name="username" value="${(login.username!'')}" type="text" autofocus autocomplete="username"
                                   aria-invalid="<#if messagesPerField.existsError('username')>true</#if>"
                                   placeholder="${msg("enterEmail")}">
                            <#if messagesPerField.existsError('username')>
                                <span class="input-error">${kcSanitize(messagesPerField.getFirstError('username'))?no_esc}</span>
                            </#if>
                        </div>

                        <div class="form-group">
                            <label for="password">${msg("password")}</label>
                            <div class="password-wrapper">
                                <input tabindex="2" id="password" name="password" type="password" autocomplete="current-password"
                                       aria-invalid="<#if messagesPerField.existsError('password')>true</#if>"
                                       placeholder="${msg("enterPassword")}">
                                <button type="button" class="password-toggle" onclick="togglePassword()" aria-label="Toggle password visibility">
                                    <svg id="eye-open" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                                        <circle cx="12" cy="12" r="3"></circle>
                                    </svg>
                                    <svg id="eye-closed" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none;">
                                        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                                        <line x1="1" y1="1" x2="23" y2="23"></line>
                                    </svg>
                                </button>
                            </div>
                            <#if messagesPerField.existsError('password')>
                                <span class="input-error">${kcSanitize(messagesPerField.getFirstError('password'))?no_esc}</span>
                            </#if>
                        </div>

                        <div id="kc-form-options">
                            <#if realm.resetPasswordAllowed>
                                <a tabindex="5" href="${url.loginResetCredentialsUrl}" class="forgot-password">${msg("doForgotPassword")}</a>
                            </#if>
                        </div>

                        <div id="kc-form-buttons">
                            <input type="hidden" id="id-hidden-input" name="credentialId">
                            <input tabindex="4" name="login" id="kc-login" type="submit" value="${msg("doLogIn")}">
                        </div>
                    </form>
            </div>
        </div>
        </#if>

        <#if realm.password && social.providers??>
        <div id="kc-social-providers">
            <div class="social-divider">
                <span>${msg("identity-provider-login-label")}</span>
            </div>
            <ul>
                <#list social.providers as p>
                <li>
                    <a id="social-${p.alias}" href="${p.loginUrl}" class="social-button">
                        ${p.displayName!}
                    </a>
                </li>
                </#list>
            </ul>
        </div>
        </#if>

        </div>

        <!-- Registration link -->
        <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
            <div id="kc-registration">
                <span>${msg("noAccount")}</span>
                <a tabindex="6" href="${url.registrationUrl}">${msg("doRegister")}</a>
            </div>
        </#if>
    </div>
    </#if>
</@layout.registrationLayout>

<script>
function togglePassword() {
    const passwordInput = document.getElementById('password');
    const eyeOpen = document.getElementById('eye-open');
    const eyeClosed = document.getElementById('eye-closed');

    if (passwordInput.type === 'password') {
        passwordInput.type = 'text';
        eyeOpen.style.display = 'none';
        eyeClosed.style.display = 'block';
    } else {
        passwordInput.type = 'password';
        eyeOpen.style.display = 'block';
        eyeClosed.style.display = 'none';
    }
}
</script>
