import os
import re
import shutil

import streamlit as st

from config import DATA_DIR, MIN_PASSWORD_LENGTH
from models import UserProfile
from storage import (
    delete_profile,
    has_education,
    has_knowledge_base,
    has_skills,
    list_profiles,
    load_profile,
    migrate_legacy_data,
    save_profile,
)


def _is_authenticated(profile_action: str) -> bool:
    return st.session_state.get("profile_authenticated", "") == profile_action


def _render_login_form(profile_action: str) -> bool:
    st.sidebar.markdown("---")
    st.sidebar.subheader("Acceso")
    password_input = st.sidebar.text_input(
        "Contraseña del perfil",
        type="password",
        key=f"login_password_{profile_action}",
    )
    if st.sidebar.button("Acceder al perfil", key="profile_login_btn", type="primary"):
        data = load_profile(profile_action)
        if data:
            profile = UserProfile.from_dict(data)
            if profile.verify_password(password_input):
                st.session_state["active_profile"] = profile
                st.session_state["profile_authenticated"] = profile_action
                st.rerun()
            else:
                st.sidebar.error("Contraseña incorrecta.")
    return False


def _render_profile_details(profile: UserProfile) -> UserProfile:
    has_exp = has_knowledge_base(profile.slug)
    has_sk = has_skills(profile.slug)
    has_ed = has_education(profile.slug)

    if not has_exp or not has_sk or not has_ed:
        migrated = migrate_legacy_data(profile.slug)
        if migrated > 0:
            st.sidebar.success(f"Se migraron {migrated} archivo(s) de datos existentes a tu perfil.")

    with st.sidebar.expander("Editar perfil", expanded=False), st.form("edit_profile_form"):
        new_full_name = st.text_input("Nombre completo", value=profile.full_name)
        new_email = st.text_input("Email", value=profile.email)
        new_phone = st.text_input("Teléfono", value=profile.phone)
        new_linkedin = st.text_input("LinkedIn URL", value=profile.linkedin_url)
        new_github = st.text_input("GitHub URL", value=profile.github_url)

        st.markdown("---")
        new_password = st.text_input(
            "Nueva contraseña (dejar vacío para no cambiar)",
            type="password",
            placeholder="Mínimo 4 caracteres",
        )
        new_password_confirm = st.text_input(
            "Confirmar nueva contraseña",
            type="password",
        )

        if st.form_submit_button("Guardar cambios"):
            if new_password and len(new_password) < MIN_PASSWORD_LENGTH:
                st.error(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
            elif new_password and new_password != new_password_confirm:
                st.error("Las contraseñas no coinciden.")
            else:
                updated = UserProfile(
                    username=profile.username,
                    full_name=new_full_name.strip(),
                    email=new_email.strip(),
                    phone=new_phone.strip(),
                    linkedin_url=new_linkedin.strip(),
                    github_url=new_github.strip(),
                    password_hash=profile.password_hash,
                    salt=profile.salt,
                )
                if new_password:
                    updated.set_password(new_password)
                save_profile(profile.username, updated.to_dict())
                st.session_state["active_profile"] = updated
                st.success("Perfil actualizado.")
                st.rerun()

    has_exp = has_knowledge_base(profile.slug)
    has_sk = has_skills(profile.slug)
    has_ed = has_education(profile.slug)
    completed = sum([has_exp, has_sk, has_ed])
    total = 3

    st.sidebar.markdown("---")
    st.sidebar.subheader(":material/checklist: Estado del perfil")
    progress_pct = int(completed / total * 100)
    st.sidebar.progress(completed / total, text=f"{progress_pct}% completado")
    icon_exp = ":material/check_circle:" if has_exp else ":material/radio_button_unchecked:"
    icon_sk = ":material/check_circle:" if has_sk else ":material/radio_button_unchecked:"
    icon_ed = ":material/check_circle:" if has_ed else ":material/radio_button_unchecked:"
    st.sidebar.markdown(f"{icon_exp} Experiencia laboral")
    st.sidebar.markdown(f"{icon_sk} Habilidades")
    st.sidebar.markdown(f"{icon_ed} Educación")
    if completed < total:
        st.sidebar.caption("Completa los 3 elementos para generar tu CV.")

    return profile


def render_profile_sidebar() -> UserProfile | None:
    st.sidebar.header("Perfil")

    existing_profiles = list_profiles()

    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        profile_action = st.selectbox(
            "Seleccionar o crear perfil",
            ["+ Nuevo Perfil"] + existing_profiles,
            key="profile_selector",
        )
    with col2:
        if profile_action != "+ Nuevo Perfil":
            delete_key = f"confirm_delete_{profile_action}"
            if delete_key not in st.session_state:
                st.session_state[delete_key] = False

            if st.button("Eliminar perfil", key="delete_profile_btn", help="Eliminar perfil"):
                st.session_state[delete_key] = True
                st.rerun()

            if st.session_state[delete_key]:
                st.warning(f"Estás por eliminar permanentemente el perfil **{profile_action}** y todos sus datos.")
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if st.button("Cancelar", key="cancel_delete_btn"):
                        st.session_state[delete_key] = False
                        st.rerun()
                with col_c2:
                    if st.button("Confirmar eliminación", key="confirm_delete_btn", type="primary"):
                        delete_profile(profile_action)
                        profile_dir = os.path.join(DATA_DIR, profile_action)
                        if os.path.exists(profile_dir):
                            shutil.rmtree(profile_dir)
                        st.session_state.pop("active_profile", None)
                        st.session_state.pop("profile_authenticated", None)
                        st.session_state[delete_key] = False
                        st.rerun()

    if profile_action == "+ Nuevo Perfil":
        with st.sidebar.form("new_profile_form"):
            username = st.text_input("Nombre de usuario", placeholder="ej: juan_perez")
            full_name = st.text_input("Nombre completo", placeholder="ej: Juan Pérez")
            email = st.text_input("Email", placeholder="ej: juan@email.com")
            phone = st.text_input("Teléfono", placeholder="ej: +57 300 123 4567")
            linkedin = st.text_input("LinkedIn URL", placeholder="https://linkedin.com/in/...")
            github = st.text_input("GitHub URL", placeholder="https://github.com/...")
            password = st.text_input("Contraseña", type="password", placeholder="Mínimo 4 caracteres")
            password_confirm = st.text_input("Confirmar contraseña", type="password")

            if st.form_submit_button("Crear Perfil", type="primary"):
                if not username.strip():
                    st.error("El nombre de usuario es obligatorio.")
                elif not password or len(password) < MIN_PASSWORD_LENGTH:
                    st.error(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
                elif password != password_confirm:
                    st.error("Las contraseñas no coinciden.")
                else:
                    slug = re.sub(r"[^a-zA-Z0-9_\-]", "", username.strip().lower().replace(" ", "_"))
                    profile = UserProfile(
                        username=slug,
                        full_name=full_name.strip(),
                        email=email.strip(),
                        phone=phone.strip(),
                        linkedin_url=linkedin.strip(),
                        github_url=github.strip(),
                    )
                    profile.set_password(password)
                    save_profile(slug, profile.to_dict())
                    st.session_state["active_profile"] = profile
                    st.session_state["profile_authenticated"] = slug
                    migrated = migrate_legacy_data(slug)
                    if migrated > 0:
                        st.sidebar.success(f"Se migraron {migrated} archivo(s) de datos existentes a '{slug}'.")
                    st.success(f"Perfil '{slug}' creado.")
                    st.rerun()

    if profile_action != "+ Nuevo Perfil":
        if _is_authenticated(profile_action):
            data = load_profile(profile_action)
            if data:
                profile = UserProfile.from_dict(data)
                st.session_state["active_profile"] = profile
                _render_profile_details(profile)
                return profile
        else:
            data = load_profile(profile_action)
            if data:
                profile = UserProfile.from_dict(data)
                if not profile.has_password:
                    st.session_state["active_profile"] = profile
                    st.session_state["profile_authenticated"] = profile_action
                    st.sidebar.info("Este perfil no tiene contraseña. Puedes establecer una en 'Editar perfil'.")
                    _render_profile_details(profile)
                    return profile
                else:
                    _render_login_form(profile_action)

    return None
