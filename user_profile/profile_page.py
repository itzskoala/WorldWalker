#profile_page.py

from sqlalchemy.orm import Session

from database.models import User


def get_profile_photo(user: User):
    return user.profile_photo


def set_profile_photo(session: Session, user: User, photo_url):
    user.profile_photo = photo_url
    session.commit()


def get_username(user: User):
    return user.username


def set_username(session: Session, user: User, username):
    user.username = username
    session.commit()


def get_f_name(user: User):
    return user.f_name


def set_f_name(session: Session, user: User, f_name):
    user.f_name = f_name
    session.commit()


def get_l_name(user: User):
    return user.l_name


def set_l_name(session: Session, user: User, l_name):
    user.l_name = l_name
    session.commit()


def get_lifetime_steps(user: User):
    return user.lifetime_steps


def get_postcards_sum(user: User):
    return user.postcards_sum

def get_bio(user: User):
    return user.bio


def set_user_bio(session: Session, user: User, bio):
    user.bio = bio
    session.commit()


def get_member_since(user: User):
    return user.member_since

def delete_account():
    pass
