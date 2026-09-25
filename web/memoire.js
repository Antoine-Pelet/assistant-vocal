/* Mémoire : aucune écriture n'est envoyée sans affichage d'une proposition distincte. */
(() => {
  const route = '/api/panneau/memoire';
  let zones = [], proposition = null, edition = null, regle = null, acces = null, charge = false;
  let decalage = 0, historiqueAcces = {}, generationVue = 0, journalChanger = false;
  const categories = {facts:'Fait', preferences:'Préférence', people:'Personne', projects:'Projet'};
  const actions = {ajouter:'Ajout', modifier:'Modification', supprimer:'Suppression', zone_creer:'Création de zone', zone_modifier:'Conditions modifiées', zone_supprimer:'Zone supprimée', expiration:'Suppression programmée', historique_mot_de_passe:'Mot de passe de l’historique changé'};
  const date = t => t == null ? 'Sans limite' : new Date(t*1000).toLocaleString('fr-FR');
  const msg = r => { $('#mem-message').textContent = r.message || ''; $('#mem-message').style.color = r.ok ? 'var(--ok)' : 'var(--ko)'; };
  const bouton = (texte, fn, danger=false) => {
    const b=document.createElement('button'); b.type='button'; b.className='act '+(danger?'danger':'ghost'); b.textContent=texte; b.onclick=fn; return b;
  };
  function fermerEditeur() { $('#mem-entree').reset(); $('#mem-entree').hidden=true; edition=null; }
  function fermerRegles() { $('#mem-regles').reset(); $('#mem-regles').hidden=true; $('#mem-pass-ligne').hidden=true; $('#mem-pass').required=false; $('#mem-pass2').required=false; $('#mem-pass-old').required=false; $('#mem-pass-old-ligne').hidden=true; $('#mem-pass2-ligne').hidden=true; regle=null; }
  async function annuler() {
    const p=proposition; proposition=null; $('#mem-validation').close(); $('#mem-resume').textContent=''; $('#mem-detail').replaceChildren();
    if(p) await post(route+'/annuler',{jeton:p.jeton});
  }
  async function proposer(action,valeurs) {
    const r=await post(route+'/proposer',{action,valeurs});
    if(!r.ok){msg(r);return;}
    proposition={...r,zone:valeurs.zone};
    $('#mem-resume').textContent=r.resume;
    const d=$('#mem-detail'); d.replaceChildren();
    if(action.startsWith('zone_') && action!=='zone_supprimer') {
      for(const [label,val] of [['Zone',r.detail.nom],['Début',date(r.detail.debut)],['Fin',date(r.detail.fin)],['Mot de passe',r.detail.mot_de_passe]]) {
        const p=document.createElement('p');p.textContent=label+' : '+val;d.append(p);
      }
    }
    $('#mem-confirmer').disabled=false; $('#mem-validation').showModal(); $('#mem-annuler').focus();
  }
  async function charger() {
    if(charge)return;charge=true; const lecture=generationVue;
    try {
      const r=await api(route); if(!r.ok){msg(r);effacer();return;}
      if(lecture!==generationVue)return;
      // La réponse contient déjà ce changement : ignorer sa notification SSE retardée.
      generationServeur=r.generation;
      decalage=r.maintenant-Date.now()/1000; zones=r.zones; historiqueAcces=r.historique_acces; dessiner();
      $('#mem-historique-verrouiller').hidden=!historiqueAcces.ouvert;
      $('#mem-historique-acces').hidden=historiqueAcces.ouvert;
      $('#mem-historique-password').hidden=!historiqueAcces.initialise;
      $('#mem-historique-etat').textContent=!historiqueAcces.initialise ? 'Choisis ton mot de passe au premier accès. Il est nécessaire avant le premier changement de mémoire.' : (historiqueAcces.ouvert?'Historique déverrouillé pour cette session.':'Historique verrouillé.');
      if(!historiqueAcces.ouvert){$('#mem-historique').replaceChildren();return;}
      const h=await api(route+'/historique'); if(!h.ok){msg(h);return;}
      if(lecture!==generationVue)return;
      const t=$('#mem-historique');t.replaceChildren();
      for(const e of h.historique) {
        const tr=document.createElement('tr');tr.dataset.expire=e.expire;
        const lib=actions[e.action]||e.action;
        for(const valeur of [date(e.cree),lib+(e.elements.length?' · '+e.elements.length+' élément(s)':''),e.zone,date(e.expire)]) {
          const td=document.createElement('td');td.textContent=valeur;tr.append(td);
        }t.append(tr);
      }
      if(!t.children.length)t.innerHTML='<tr><td colspan="4" class="muted">Aucun changement au cours des sept derniers jours.</td></tr>';
    } finally {charge=false;if(lecture!==generationVue&&!document.hidden&&$('#memoire').classList.contains('on'))setTimeout(charger,0);}
  }
  function dessiner() {
    const cont=$('#mem-zones');cont.replaceChildren();
    for(const z of zones) {
      const card=document.createElement('div');card.className='card';card.dataset.zone=z.id;
      const titre=document.createElement('h2');titre.textContent=z.nom;card.append(titre);
      const detail=document.createElement('p');detail.className='muted';
      detail.textContent=(z.accessible?'Accessible':'Verrouillée')+(z.protegee?' · Mot de passe':'')+
        (z.debut!=null?' · À partir du '+date(z.debut):'')+(z.fin!=null?' · Jusqu’au '+date(z.fin):'')+
        (z.session_fin?' · Session jusqu’au '+date(z.session_fin):'');card.append(detail);
      const row=document.createElement('div');row.className='row';card.append(row);
      if(z.protegee) {
        row.append(bouton(z.session_fin?'Verrouiller':'Déverrouiller',async()=>{
          if(z.session_fin){const r=await post(route+'/verrouiller',{zone:z.id});fermerEditeur();await annuler();msg(r);await charger();}
          else{acces=z.id;$('#mem-acces-message').textContent='';$('#mem-acces-titre').textContent='Déverrouiller « '+z.nom+' »';$('#mem-acces').showModal();$('#mem-secret').focus();}
        }));
      }
      if(z.id!=='generale') {
        row.append(bouton('Conditions d’accès',()=>editerZone(z)));
        row.append(bouton('Supprimer la zone',()=>proposer('zone_supprimer',{zone:z.id}),true));
      }
      if(z.accessible) {
        row.append(bouton('Ajouter un souvenir',()=>editerEntree(z)));
        for(const e of z.entrees) {
          const ligne=document.createElement('div');ligne.className='fld';
          const texte=document.createElement('div');texte.className='mem-texte';
          const label=document.createElement('small');label.className='muted';label.textContent=categories[e.categorie]+(e.cle?' · '+e.cle:'')+(e.expiration?' · Suppression le '+date(e.expiration):' · Sans limite de durée');
          const contenu=document.createElement('div');contenu.textContent=e.contenu;texte.append(label,contenu);ligne.append(texte);
          ligne.append(bouton('Modifier',()=>editerEntree(z,e)),bouton('Supprimer',()=>proposer('supprimer',{zone:z.id,id:e.id}),true));card.append(ligne);
        }
        if(!z.entrees.length){const p=document.createElement('p');p.className='muted';p.textContent='Aucun souvenir dans cette zone.';card.append(p);}
      } else {const p=document.createElement('p');p.textContent=z.raison;card.append(p);}
      cont.append(card);
    }
    if(!$('#mem-entree').hidden && !zones.find(z=>z.id===$('#mem-zone').value)?.accessible)fermerEditeur();
  }
  function editerEntree(zone,entree=null) {
    fermerRegles();fermerEditeur();
    const s=$('#mem-zone');s.replaceChildren();
    for(const z of zones.filter(z=>z.accessible)){const o=document.createElement('option');o.value=z.id;o.textContent=z.nom;s.append(o);}
    if(zone)s.value=zone.id;s.disabled=!!entree;edition=entree?.id||null;
    if(!s.options.length){msg({ok:false,message:'Déverrouille d’abord une zone.'});return;}
    $('#mem-entree-titre').textContent=entree?'Modifier le souvenir':'Ajouter un souvenir';
    $('#mem-categorie').value=entree?.categorie||'facts';$('#mem-cle').value=entree?.cle||'';$('#mem-contenu').value=entree?.contenu||'';
    $('#mem-expiration').value=dateLocale(entree?.expiration);
    $('#mem-entree').hidden=false;$('#mem-contenu').focus();$('#mem-entree').scrollIntoView({block:'center',behavior:'smooth'});
  }
  function dateLocale(t) {if(t==null)return '';const d=new Date(t*1000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,19);}
  function editerZone(z=null) {
    fermerEditeur();fermerRegles();regle=z?.id||null;
    $('#mem-regles-titre').textContent=z?'Modifier les conditions d’accès':'Créer une zone';
    $('#mem-nom').value=z?.nom||'';$('#mem-debut').value=dateLocale(z?.debut);$('#mem-fin').value=dateLocale(z?.fin);
    $('#mem-pass-old-ligne').hidden=!z?.protegee;$('#mem-pass-old').required=!!z?.protegee;
    $('#mem-regles').hidden=false;$('#mem-nom').focus();$('#mem-regles').scrollIntoView({block:'center',behavior:'smooth'});
  }
  function effacer(){zones=[];$('#mem-zones').replaceChildren();$('#mem-historique').replaceChildren();fermerEditeur();fermerRegles();annuler();$('#mem-secret').value='';}
  $('#mem-entree').onsubmit=async e=>{
    e.preventDefault();await proposer(edition?'modifier':'ajouter',{zone:$('#mem-zone').value,id:edition,categorie:$('#mem-categorie').value,cle:$('#mem-cle').value,contenu:$('#mem-contenu').value,expiration:$('#mem-expiration').value?new Date($('#mem-expiration').value).toISOString():null});
  };
  $('#mem-regles').onsubmit=async e=>{
    e.preventDefault();if($('#mem-pass-action').value==='definir' && $('#mem-pass').value!==$('#mem-pass2').value){msg({ok:false,message:'Les mots de passe ne correspondent pas.'});return;}const iso=id=>$(id).value?new Date($(id).value).toISOString():null;
    const valeurs={zone:regle,nom:$('#mem-nom').value,debut:iso('#mem-debut'),fin:iso('#mem-fin'),mot_de_passe_action:$('#mem-pass-action').value,mot_de_passe:$('#mem-pass').value,ancien_mot_de_passe:$('#mem-pass-old').value};
    $('#mem-pass').value='';$('#mem-pass2').value='';$('#mem-pass-old').value='';await proposer(regle?'zone_modifier':'zone_creer',valeurs);
  };
  $('#mem-pass-action').onchange=()=>{$('#mem-pass-ligne').hidden=$('#mem-pass-action').value!=='definir';$('#mem-pass').required=!$('#mem-pass-ligne').hidden;$('#mem-pass2-ligne').hidden=$('#mem-pass-ligne').hidden;$('#mem-pass2').required=!$('#mem-pass2-ligne').hidden;$('#mem-pass-old-ligne').hidden=!zones.find(z=>z.id===regle)?.protegee;$('#mem-pass-old').required=!$('#mem-pass-old-ligne').hidden;};
  $('#mem-confirmer').onclick=async()=>{
    if(!proposition)return;$('#mem-confirmer').disabled=true;
    const r=await post(route+'/confirmer',{jeton:proposition.jeton});proposition=null;await annuler();msg(r);
    if(r.ok){fermerEditeur();fermerRegles();}await charger();
  };
  $('#mem-annuler').onclick=annuler;$('#mem-validation').addEventListener('cancel',annuler);
  $('#mem-deverrouiller').onsubmit=async e=>{
    e.preventDefault();const mot=$('#mem-secret').value;$('#mem-secret').value='';
    const r=await post(route+'/deverrouiller',{zone:acces,mot_de_passe:mot});
    if(r.ok){$('#mem-acces').close();msg(r);await charger();}else $('#mem-acces-message').textContent=r.message;
  };
  $('#mem-acces-annuler').onclick=()=>{$('#mem-secret').value='';$('#mem-acces').close();};
  $('#mem-acces').addEventListener('cancel',()=>{$('#mem-secret').value='';});
  $('#mem-ajouter').onclick=()=>editerEntree(zones.find(z=>z.id==='generale'));
  $('#mem-zone-creer').onclick=()=>editerZone();$('#mem-actualiser').onclick=charger;
  $('#mem-fermer-entree').onclick=fermerEditeur;$('#mem-fermer-regles').onclick=fermerRegles;
  function fermerJournal(){ $('#mem-journal-form').reset();$('#mem-journal-dialog').close(); }
  function ouvrirJournal(changer=false){
    journalChanger=changer;$('#mem-journal-form').reset();$('#mem-journal-message').textContent='';
    $('#mem-journal-titre').textContent=changer?'Changer le mot de passe de l’historique':'Choisir le mot de passe de l’historique';
    $('#mem-journal-old-ligne').hidden=!changer;$('#mem-journal-old').required=changer;
    $('#mem-journal-dialog').showModal();$('#mem-journal-new').focus();
  }
  $('#mem-historique-acces').onclick=()=>{
    if(!historiqueAcces.initialise){ouvrirJournal();return;}
    acces='_historique';$('#mem-acces-message').textContent='';$('#mem-acces-titre').textContent='Déverrouiller l’historique';$('#mem-acces').showModal();$('#mem-secret').focus();
  };
  $('#mem-historique-verrouiller').onclick=async()=>{const r=await post(route+'/verrouiller',{zone:'_historique'});$('#mem-historique').replaceChildren();msg(r);await charger();};
  $('#mem-historique-password').onclick=()=>ouvrirJournal(true);
  $('#mem-journal-fermer').onclick=fermerJournal;
  $('#mem-journal-dialog').addEventListener('cancel',fermerJournal);
  $('#mem-journal-form').onsubmit=async e=>{
    e.preventDefault();if($('#mem-journal-new').value!==$('#mem-journal-repeat').value){$('#mem-journal-message').textContent='Les mots de passe ne correspondent pas.';return;}
    const valeurs={mot_de_passe:$('#mem-journal-new').value,ancien_mot_de_passe:$('#mem-journal-old').value};
    const action=journalChanger?'historique_mot_de_passe':'historique_initialiser';fermerJournal();await proposer(action,valeurs);
  };
  const evenements=new EventSource(route+'/evenements');let generationServeur=null;
  evenements.onmessage=e=>{
    const nouvelle=Number(e.data);
    if(generationServeur!==null && nouvelle>generationServeur){
      generationVue++;effacer();
      setTimeout(()=>{if($('#memoire').classList.contains('on'))charger();},100);
    }
    generationServeur=Math.max(generationServeur??nouvelle,nouvelle);
  };
  evenements.onerror=()=>{generationServeur=null;generationVue++;effacer();};
  window.chargerMemoire=charger;
  // Retirer immédiatement les valeurs expirées, même si le prochain appel réseau échoue.
  setInterval(()=>{
    const now=Date.now()/1000+decalage;
    for(const z of zones) if(z.accessible && ((z.fin!=null&&now>=z.fin)||(z.session_fin&&now>=z.session_fin))) {
      z.accessible=false;z.entrees=[];z.raison='Accès expiré.';fermerEditeur();annuler();dessiner();
    }
    if(historiqueAcces.session_fin && now>=historiqueAcces.session_fin){$('#mem-historique').replaceChildren();historiqueAcces.ouvert=false;}
    for(const tr of $$('#mem-historique tr[data-expire]'))if(now>=Number(tr.dataset.expire))tr.remove();
    if(proposition&&now>=proposition.expire)annuler();
  },250);
  setInterval(()=>{if($('#memoire').classList.contains('on')&&!document.hidden)charger();},5000);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)effacer();else if($('#memoire').classList.contains('on'))charger();});
})();
