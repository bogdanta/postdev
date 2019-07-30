import onemsdk
import datetime
import jwt
import pytz
import requests
import string

from ago import human
from hashids import Hashids

from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.views.generic import View as _View
from django.shortcuts import get_object_or_404

from onemsdk.schema.v1 import (
    Response, Menu, MenuItem, MenuItemType, Form, FormItemContent, FormItemMenu,
    FormItemContentType, FormItemMenuItem, FormItemMenuItemType, FormMeta
)

from .models import Post


class View(_View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *a, **kw):
        return super(View, self).dispatch(*a, **kw)

    def get_user(self):
        token = self.request.headers.get('Authorization')
        if token is None:
            raise PermissionDenied

        data = jwt.decode(token.replace('Bearer ', ''), key='87654321')
        user, created = User.objects.get_or_create(id=data['sub'])

        return user

    def to_response(self, content):
        response = Response(content=content)

        return HttpResponse(response.json(), content_type='application/json')


class HomeView(View):
    http_method_names = ['get','post', 'put']

    def get(self, request, post_id=None):
        user = self.get_user()
        if user.username == '':
            form_items = [
                FormItemContent(type=FormItemContentType.string,
                                name='username',
                                description='Please choose a username',
                                header='MENU',
                                footer='Send username')
            ]
            content = Form(body=form_items,
                           method='POST',
                           path=reverse('home'),
                           meta=FormMeta(confirmation_needed=False,
                                         completion_status_in_header=False,
                                         completion_status_show=False))
        else:
            menu_items = [
                MenuItem(description='Add post',
                         method='GET',
                         path=reverse('add_post')),
                MenuItem(description='Search',
                         method='GET',
                         path=reverse('search_wizard')),
                MenuItem(description='My posts',
                         method='GET',
                         path=reverse('my_posts'))
            ]
            
            posts = Post.objects.exclude(
                user=self.get_user()
            ).exclude(
                is_private=True
                ).order_by('-created_at').all()[:3]
            if posts:
                for post in posts:
                    menu_items.append(
                        MenuItem(description=u'{}..'.format(post.title[:17]),
                                 method='GET',
                                 path=reverse('post_detail', args=[post.id]))
                    )

            content = Menu(body=menu_items)

        return self.to_response(content)

    def post(self, request):
        user = self.get_user()
        User.objects.filter(id=user.id).update(username=request.POST['username'])
        return HttpResponseRedirect(reverse('home'))


class AddPostView(View):
    http_method_names = ['get', 'post']

    def get(self, request):
        form_items = [
            FormItemContent(type=FormItemContentType.string,
                     name='title',
                     description='Give your new post a title (maximum 64 characters',
                     header='add',
                     footer='Reply with post title or BACK'),
            FormItemContent(type=FormItemContentType.string,
                     name='description',
                     description='Send post content (max 50 words)',
                     header='add',
                     footer='Reply with post content or BACK'),
            FormItemMenu(body=[FormItemMenuItem(description='Private (share code)',
                                                value='True'),
                               FormItemMenuItem(description='Public (everyone)',
                                                value='False')],
                         name='is_private')
        ]
        form = Form(body=form_items,
                    method='POST',
                    path=reverse('add_post'),
                    meta=FormMeta(confirmation_needed=False,
                                  completion_status_in_header=False,
                                  completion_status_show=False))

        return self.to_response(form)

    def post(self, request):
        now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        expires_at = now + datetime.timedelta(days=14)
        user_id = self.get_user().id

        new_post = Post.objects.create(
            user=self.get_user(),
            title=request.POST['title'],
            description=request.POST['description'],
            is_private=request.POST['is_private'],
            created_at=now,
            expires_at=expires_at,
            views=0,
        )

        hashids = Hashids(salt=str(user_id),
                          alphabet=string.ascii_lowercase + string.digits,
                          min_length=6)
        
        new_post.code = hashids.encode(new_post.id)
        new_post.save()

        return HttpResponseRedirect(reverse('post_detail', args=[new_post.id]))


class MyPostsListView(View):
    http_method_names = ['get']

    def get(self, request):
        # TODO: later improvement - check for expired posts
        menu_items = []
        posts = Post.objects.filter(user=self.get_user()).order_by('-created_at')
        if posts:
            for post in posts:
                menu_items.append(
                    MenuItem(description=u'{}..'.format(post.title[:15]),
                             method='GET',
                             path=reverse('post_detail', args=[post.id]))
                )
        else:
            menu_items.append(
                MenuItem(description='You currently have no posts.')
            )
        content = Menu(body=menu_items)
        
        return self.to_response(content)


class PostDetailView(View):
    http_method_names = ['get', 'put', 'patch', 'delete']

    def get(self, request, id):
        post = get_object_or_404(Post, id=id)
        post.views += 1
        post.save()

        menu_items = [
            MenuItem(description=u'\n'.join([
                post.description,
                'Author: {}'.format(post.user.username),
                'Expires in: {}'.format(human(post.expires_at)),
                'Code: {}'.format(post.code),
                'Views: {}'.format(post.views)]))
        ]

        if post.user == self.get_user():
            # viewing user is the post owner
            menu_items.extend([
                MenuItem(description='Renew',
                         method='PATCH',
                         path=reverse('post_detail', args=[post.id])),
                MenuItem(description='Delete',
                         method='DELETE',
                         path=reverse('post_detail', args=[post.id]))
           ])
            if not post.is_private:
                menu_items.extend([
                    MenuItem(description='Make private',
                             method='PUT',
                             path=reverse('post_detail', args=[post.id]))
               ])

        else:
             menu_items.extend([
                 MenuItem(description='Send message',
                          method='GET',
                          path=reverse('home')),
                 MenuItem(description='Comments',
                          method='GET',
                          path=reverse('home'))
            ])

        content = Menu(body=menu_items, header=post.title)

        return self.to_response(content)

    def put(self, request, id):
        # method currently used only for marking a public post as private
        post = get_object_or_404(Post, id=id)                                    
        post.is_private = True
        post.save()
        return HttpResponseRedirect(reverse('post_detail', args=[id]))


    def delete(self, request, id):
        post = get_object_or_404(Post, id=id)                                    
        post.delete()
        return HttpResponseRedirect(reverse('my_posts'))

    def patch(self, request, id):
        # method currently used only for renewing an existing post validity
        post = get_object_or_404(Post, id=id)
        now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        expires_at = now + datetime.timedelta(days=14)
        post.expires_at = expires_at
        post.save()
        return HttpResponseRedirect(reverse('post_detail', args=[id]))


class SearchWizardView(View):
    http_method_names = ['get', 'post']
    # see def filtered_search in api/services/post.py - exclude expired, check if code, match username, post title, post bodies

    def post(self, request):
        pass
        # this will take a keyword and display a list of matching results

    def get(seld, request, id):
        pass
        # this will redirect to post_detail with that specific id
    
