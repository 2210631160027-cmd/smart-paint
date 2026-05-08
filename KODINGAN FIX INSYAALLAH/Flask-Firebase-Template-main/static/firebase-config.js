import { initializeApp } from "https://www.gstatic.com/firebasejs/10.9.0/firebase-app.js";
import { getAuth, 
         GoogleAuthProvider } from "https://www.gstatic.com/firebasejs/10.9.0/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/10.9.0/firebase-firestore.js";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyDUUYsYskvAeS3yC3Ij5OvjNLqIBxd5Jmc",
  authDomain: "deteksi-body.firebaseapp.com",
  projectId: "deteksi-body",
  storageBucket: "deteksi-body.firebasestorage.app",
  messagingSenderId: "795367096827",
  appId: "1:795367096827:web:ae45c619487fcf085c8b5e",
  measurementId: "G-SDT6HDZQN2"
};

  // Initialize Firebase
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const provider = new GoogleAuthProvider();

const db = getFirestore(app);

export { auth, provider, db };