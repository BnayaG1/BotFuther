/**
 * בניה גיל - מערכות לימוד חכמות
 * אינטראקטיביות וסימולטור בוט סטטיקה
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. הגדרת שנת זכויות יוצרים עדכנית
  const yearElement = document.getElementById('current-year');
  if (yearElement) {
    yearElement.textContent = new Date().getFullYear();
  }

  // 2. נתוני שיחות לדוגמה עבור סימולטור הבוט
  const botConversations = {
    reactions: {
      userQuestion: "איך מחשבים ראקציות בסמכים לקורה עם עומס משולש ומפורס?",
      botResponse: `
        <div>
          <p><strong>שלום! בוא נפרק את חישוב הראקציות ל-3 צעדים ברורים:</strong></p>
          <ul class="sim-step-list">
            <li><strong>1. שקול כוחות:</strong> נחליף את העומס המפורס המשולש בכוח מרוכז ששווה לשטח המשולש: <code>W = 0.5 &times; q &times; L</code> הפועל במרחק שליש מהבסיס הרחב.</li>
            <li><strong>2. משוואת מומנטים:</strong> נבצע סכום מומנטים סביב הסמך הפירקי (ΣM = 0) כדי לבודד ולמצוא את הראקציה האנכית בסמך הנייד.</li>
            <li><strong>3. שיווי משקל כוחות:</strong> נשתמש ב-<code>ΣFy = 0</code> למציאת הראקציה השנייה, וב-<code>ΣFx = 0</code> לבדיקת כוחות אופקיים.</li>
          </ul>
          <div class="sim-code-preview">
            ΣM_A = 0 ➔ R_B &times; L - W &times; (x_w) = 0 ➔ R_B = (W &times; x_w) / L
          </div>
        </div>
      `
    },
    truss: {
      userQuestion: "איך יודעים באיזה שיטה לפתור מסבך – צמתים או חתכים (ריטר)?",
      botResponse: `
        <div>
          <p><strong>כלל אצבע מנצח למבחן בסטטיקה:</strong></p>
          <ul class="sim-step-list">
            <li><strong>שיטת הצמתים (Joints):</strong> מעולה כאשר מבקשים את הכוחות <em>בכל</em> מוטות המסבך, או כשיש צומת עם מקסימום 2 נעלמים.</li>
            <li><strong>שיטת החתכים (Ritter):</strong> הדרך המהירה ביותר כאשר מבקשים כוח במוטות <em>ספציפיים בלבד</em> במרכז המסבך (מעבירים חתך שחוצה עד 3 מוטות).</li>
            <li><strong>זיהוי מוטות אפס:</strong> צומת של 2 מוטות לא קו-ליניאריים ללא כוח חיצוני ➔ שניהם שווים 0!</li>
          </ul>
          <div class="sim-code-preview">
            Joint: ΣFx = 0, ΣFy = 0 | Section: ΣM_node = 0
          </div>
        </div>
      `
    },
    centroid: {
      userQuestion: "איך מוצאים מרכז כובד ומומנט אינרציה לשטח מורכב?",
      botResponse: `
        <div>
          <p><strong>פתרון מובנה לשטחים מורכבים (T-beam / פרופיל מורכב):</strong></p>
          <ul class="sim-step-list">
            <li><strong>1. חלוקה לצורות פשוטות:</strong> נחלק את החתך למלבנים או משולשים בסיסיים ששטחם ומרכזם ידוע.</li>
            <li><strong>2. חישוב y-bar:</strong> נחשב לפי הנוסחה המשוקללת: <code>y_c = Σ(A_i &times; y_i) / ΣA_i</code>.</li>
            <li><strong>3. משפט שטיינר לאינרציה:</strong> מעבירים את האינרציה מציר מקומי לציר המרכזי הכולל: <code>I = I_0 + A &times; d^2</code>.</li>
          </ul>
          <div class="sim-code-preview">
            I_total = Σ ( (b_i &times; h_i^3) / 12 + A_i &times; d_i^2 )
          </div>
        </div>
      `
    },
    internal_forces: {
      userQuestion: "איך משרטטים מהלך מומנטים (M) וגזירה (V) בלי להתבלבל בסימנים?",
      botResponse: `
        <div>
          <p><strong>שיטת הגזירה והאינטגרל הגרפי:</strong></p>
          <ul class="sim-step-list">
            <li><strong>מהלך גזירה V:</strong> עולים ויורדים בדיוק לפי הכוחות החיצוניים (כוח מעלה ➔ קפיצה למעלה). עומס מפורס יוצר שיפוע ליניארי יורד.</li>
            <li><strong>נקודת איפוס גזירה (V = 0):</strong> זו הנקודה שבה מומנט הכפיפה M מגיע ל<strong>ערך מקסימלי</strong>!</li>
            <li><strong>מהלך מומנט M:</strong> המומנט שווה לשטח שמתחת לגרף הגזירה (<code>dM/dx = V</code>). סיב גמיש/מתוח תמיד מצויר בצד התחתון.</li>
          </ul>
          <div class="sim-code-preview">
            M(x) = ∫ V(x) dx | M_max occurs at V(x) = 0
          </div>
        </div>
      `
    }
  };

  // 3. עדכון תוכן הסימולטור בהתאם לבחירת נושא
  const simConversation = document.getElementById('sim-conversation');
  const chipButtons = document.querySelectorAll('.chip-btn');

  function renderConversation(topicKey) {
    const data = botConversations[topicKey];
    if (!data || !simConversation) return;

    simConversation.innerHTML = `
      <div class="sim-msg-user">
        ${data.userQuestion}
      </div>
      <div class="sim-msg-bot">
        ${data.botResponse}
      </div>
    `;
  }

  // הצגת נושא ברירת מחדל
  renderConversation('reactions');

  // האזנה לקליקים על צ'יפים
  chipButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      chipButtons.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const topic = btn.getAttribute('data-topic');
      renderConversation(topic);
    });
  });

  // 4. אפקט עדין של תלת-ממד לכרטיס ההירו
  const glassCard = document.querySelector('.floating-glass-card');
  if (glassCard && window.innerWidth > 992) {
    window.addEventListener('mousemove', (e) => {
      const { clientX, clientY } = e;
      const xPos = (clientX / window.innerWidth - 0.5) * 10;
      const yPos = (clientY / window.innerHeight - 0.5) * 10;
      glassCard.style.transform = `perspective(1000px) rotateY(${xPos}deg) rotateX(${-yPos}deg)`;
    });
  }
});
