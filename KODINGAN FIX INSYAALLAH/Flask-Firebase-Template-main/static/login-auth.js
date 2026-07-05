import { auth, provider } from "./firebase-config.js";

// Tambahkan signOut di daftar import ini
import { createUserWithEmailAndPassword,
         signInWithEmailAndPassword,
         signInWithPopup,
         sendPasswordResetEmail,
         signOut } from "https://www.gstatic.com/firebasejs/10.9.0/firebase-auth.js";


/* == UI - Elements == */
const signInWithGoogleButtonEl = document.getElementById("sign-in-with-google-btn")
const signUpWithGoogleButtonEl = document.getElementById("sign-up-with-google-btn")
const emailInputEl = document.getElementById("email-input")
const passwordInputEl = document.getElementById("password-input")
const signInButtonEl = document.getElementById("sign-in-btn")
const createAccountButtonEl = document.getElementById("create-account-btn")
const emailForgotPasswordEl = document.getElementById("email-forgot-password")
const forgotPasswordButtonEl = document.getElementById("forgot-password-btn")

const errorMsgEmail = document.getElementById("email-error-message")
const errorMsgPassword = document.getElementById("password-error-message")
const errorMsgGoogleSignIn = document.getElementById("google-signin-error-message")


/* == UI - Event Listeners == */
if (signInWithGoogleButtonEl && signInButtonEl) {
    signInWithGoogleButtonEl.addEventListener("click", authSignInWithGoogle)
    signInButtonEl.addEventListener("click", authSignInWithEmail)
}

if (createAccountButtonEl) {
    createAccountButtonEl.addEventListener("click", authCreateAccountWithEmail)
}

if (signUpWithGoogleButtonEl) {
    signUpWithGoogleButtonEl.addEventListener("click", authSignUpWithGoogle)
}

if (forgotPasswordButtonEl) {
    forgotPasswordButtonEl.addEventListener("click", resetPassword)
}


/* === Main Code === */

/* = Functions - Firebase - Authentication = */

// Function to sign in with Google authentication
async function authSignInWithGoogle() {
    provider.setCustomParameters({
        'prompt': 'select_account'
    });

    try {
        const result = await signInWithPopup(auth, provider);

        if (!result || !result.user) {
            throw new Error('Authentication failed: No user data returned.');
        }

        const user = result.user;
        const email = user.email;

        if (!email) {
            throw new Error('Authentication failed: No email address returned.');
        }

        const idToken = await user.getIdToken();
        loginUser(user, idToken);

    } catch (error) {
        console.error('Error during sign-in with Google', error);
    }
}

// Function to create new account with Google auth
async function authSignUpWithGoogle() {
    provider.setCustomParameters({
        'prompt': 'select_account'
    });

    try {
        const result = await signInWithPopup(auth, provider);
        const user = result.user;
        
        const idToken = await user.getIdToken();
        loginUser(user, idToken);
    } catch (error) {
        console.error("Error during Google signup: ", error.message);
    }
}


function authSignInWithEmail(e) {
    if (e && e.preventDefault) e.preventDefault();

    errorMsgEmail.style.display = "none";
    errorMsgPassword.style.display = "none";

    const email = emailInputEl.value
    const password = passwordInputEl.value

    signInWithEmailAndPassword(auth, email, password)
        .then((userCredential) => {
            const user = userCredential.user;

            user.getIdToken().then(function(idToken) {
                loginUser(user, idToken)
            });

            console.log("User signed in: ", user)
        })
        .catch((error) => {
            const errorCode = error.code;
            console.error("Error code: ", errorCode)
            if (errorCode === "auth/invalid-email") {
                errorMsgEmail.textContent = "Email tidak valid"
                errorMsgEmail.style.display = "block" 
            } else if (errorCode === "auth/invalid-credential") {
                errorMsgPassword.textContent = "Login gagal - email atau password salah"
                errorMsgPassword.style.display = "block" 
            } 
        });
}


// BAGIAN YANG DIPERBARUI: Sign Out dulu, baru munculkan notif
function authCreateAccountWithEmail(e) {
    if (e && e.preventDefault) e.preventDefault();

    if (errorMsgEmail) errorMsgEmail.style.display = "none";
    if (errorMsgPassword) errorMsgPassword.style.display = "none";

    const email = emailInputEl.value
    const password = passwordInputEl.value

    if (createAccountButtonEl) createAccountButtonEl.textContent = "Memproses...";

    createUserWithEmailAndPassword(auth, email, password)
        .then(async (userCredential) => {
            const user = userCredential.user;

            if (typeof addNewUserToFirestore === "function") {
                await addNewUserToFirestore(user);
            }
            
            // Logout di belakang layar
            await signOut(auth);

            // Munculkan notifikasi
            alert("Berhasil! Akun Anda telah dibuat. Silakan login.");

            // Beri jeda 2.5 detik (2500 milidetik) sebelum pindah halaman
            setTimeout(() => {
                window.location.href = '/login'; 
            }, 2500);

        })
        .catch((error) => {
            if (createAccountButtonEl) createAccountButtonEl.textContent = "Buat Akun";

            const errorCode = error.code;

            if (errorCode === "auth/invalid-email") {
                errorMsgEmail.textContent = "Email tidak valid"
                errorMsgEmail.style.display = "block" 
            } else if (errorCode === "auth/weak-password") {
                errorMsgPassword.textContent = "Password terlalu lemah - minimal 6 karakter"
                errorMsgPassword.style.display = "block" 
            } else if (errorCode === "auth/email-already-in-use") {
                errorMsgEmail.textContent = "Email ini sudah terdaftar. Silakan login."
                errorMsgEmail.style.display = "block" 
            } else {
                errorMsgPassword.textContent = "Terjadi kesalahan. Coba lagi."
                errorMsgPassword.style.display = "block"
            }
        });
}


function resetPassword() {
    const emailToReset = emailForgotPasswordEl.value

    clearInputField(emailForgotPasswordEl)

    sendPasswordResetEmail(auth, emailToReset)
    .then(() => {
        const resetFormView = document.getElementById("reset-password-view")
        const resetSuccessView = document.getElementById("reset-password-confirmation-page")

        if (resetFormView) resetFormView.style.display = "none"
        if (resetSuccessView) resetSuccessView.style.display = "block"
    })
    .catch((error) => {
        console.error("Reset password error: ", error);
    });
}


function loginUser(user, idToken) {
    fetch('/auth', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            idToken: idToken
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            window.location.href = '/dashboard';
        } else {
            alert(data.error || "Akses ditolak");
        }
    })
    .catch(error => {
        console.error('Fetch error:', error);
    });
}


/* = Functions - UI = */
function clearInputField(field) {
    if (field) field.value = ""
}

function clearAuthFields() {
    clearInputField(emailInputEl)
    clearInputField(passwordInputEl)
}